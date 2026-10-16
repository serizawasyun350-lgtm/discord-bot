import os
import asyncio
import datetime
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
from discord.ext import tasks

# ==========================================
# 0. Renderのポート検知 & HEADリクエスト対応 Webサーバー
# ==========================================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        return

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

server_thread = threading.Thread(target=run_web_server, daemon=True)
server_thread.start()


# ==========================================
# 1. Discord Bot の実装
# ==========================================
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.user_message_timestamps = {}
        
        self.user_moderation_records = {}
        self.user_availability_status = {}
        self.election_candidates = {}

        self.auth_role_id = None
        self.web_auth_enabled = True
        self.server_rule_text = "1. 誹謗中傷や暴言の禁止\n2. スパム・連投行為の禁止\n3. 宣伝行為は専用チャンネルでのみ許可\n4. 運営・管理者の指示に従うこと"
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        self.custom_status = None
        
        self.active_status_messages = []
        self.sticky_messages = {}

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドを同期しました。")
        self.update_status_task.start()
        self.refresh_status_messages_task.start()

    @tasks.loop(seconds=30)
    async def update_status_task(self):
        try:
            if self.custom_status:
                await self.change_presence(activity=self.custom_status)
                return

            latency = round(self.latency * 1000)
            guilds_count = len(self.guilds)
            
            statuses = [
                discord.Activity(type=discord.ActivityType.playing, name="/help で使い方を確認"),
                discord.Activity(type=discord.ActivityType.watching, name=f"{guilds_count} サーバーを監視中"),
                discord.Activity(type=discord.ActivityType.listening, name=f"Ping: {latency}ms")
            ]
            
            for status in statuses:
                if self.custom_status:
                    break
                await self.change_presence(activity=status)
                await asyncio.sleep(10)
        except Exception as e:
            print(f"ステータス自動更新エラー: {e}")

    @update_status_task.before_loop
    async def before_update_status(self):
        await self.wait_until_ready()

    @tasks.loop(seconds=1)
    async def refresh_status_messages_task(self):
        if not self.active_status_messages:
            return

        latency = round(self.latency * 1000)
        now = datetime.datetime.now(datetime.timezone.utc)
        uptime_delta = now - self.start_time
        
        hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        uptime_str = f"{days}日 {hours}時間 {minutes}分 {seconds}秒" if days > 0 else f"{hours}時間 {minutes}分 {seconds}秒"

        embed = discord.Embed(title="🟢 Bot システム稼働状況 (1秒間隔更新中)", color=discord.Color.green())
        embed.add_field(name="接続状態", value="正常稼働中 (Online)", inline=True)
        embed.add_field(name="応答速度 (Ping)", value=f"`{latency} ms`", inline=True)
        embed.add_field(name="導入サーバー数", value=f"`{len(client.guilds)}` サーバー", inline=True)
        embed.add_field(name="連続稼働時間 (Uptime)", value=f"`{uptime_str}`", inline=False)
        embed.set_footer(text=f"リアルタイム更新中 ({now.strftime('%H:%M:%S')})")

        surviving_messages = []
        for msg in self.active_status_messages:
            try:
                fetched_msg = await msg.channel.fetch_message(msg.id)
                await fetched_msg.edit(embed=embed)
                surviving_messages.append(msg)
            except Exception:
                pass
        self.active_status_messages = surviving_messages

    @refresh_status_messages_task.before_loop
    async def before_refresh_status(self):
        await self.wait_until_ready()

client = MyBot()

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")

# ==========================================
# メッセージ受信イベント（スパム検知 & 固定メッセージ追従機能）
# ==========================================
@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if not message.author.guild_permissions.administrator:
        user_id = message.author.id
        now = datetime.datetime.now(datetime.timezone.utc)

        if user_id not in client.user_message_timestamps:
            client.user_message_timestamps[user_id] = []

        timestamps = client.user_message_timestamps[user_id]
        timestamps = [t for t in timestamps if (now - t).total_seconds() < 5]
        timestamps.append(now)
        client.user_message_timestamps[user_id] = timestamps

        if len(timestamps) >= 4:
            try:
                await message.delete()
                duration = datetime.timedelta(minutes=10)
                await message.author.timeout(duration, reason="自動スパム検知による連投規制")
                
                if user_id not in client.user_moderation_records:
                    client.user_moderation_records[user_id] = {"warn_count": 0, "last_penalty": "なし"}
                
                client.user_moderation_records[user_id]["warn_count"] += 1
                client.user_moderation_records[user_id]["last_penalty"] = f"10分間タイムアウト ({now.strftime('%Y/%m/%d %H:%M')})"

                embed = discord.Embed(
                    title="⚠️ スパム検知（自動規制）",
                    description=f"{message.author.mention} 様が短時間に大量のメッセージを投稿したため、メッセージを**自動削除**し、**10分間のタイムアウト（TO）**を実行しました。",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed, delete_after=15)
                client.user_message_timestamps[user_id] = []
                return
            except Exception as e:
                print(f"スパム処理エラー: {e}")

    channel_id = message.channel.id
    if channel_id in client.sticky_messages:
        sticky_data = client.sticky_messages[channel_id]
        try:
            old_msg = await message.channel.fetch_message(sticky_data["message_id"])
            await old_msg.delete()
        except Exception:
            pass

        embed = discord.Embed(title="📌 重要なお知らせ", description=sticky_data["content"], color=discord.Color.blue())
        new_msg = await message.channel.send(embed=embed)
        client.sticky_messages[channel_id]["message_id"] = new_msg.id

# ==========================================
# UIコンポーネント & モーダル定義
# ==========================================

class TicketCreateView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 チケットを作成する", style=discord.ButtonStyle.primary, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        category = discord.utils.get(guild.categories, name="サポートチケット")
        if not category:
            try:
                category = await guild.create_category("サポートチケット")
            except Exception:
                pass

        channel_name = f"ticket-{interaction.user.name}"
        ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        
        close_view = TicketCloseView()
        embed = discord.Embed(title="🎫 サポートチケット", description=f"{interaction.user.mention} 様、お問い合わせ内容をどうぞ。\n解決したら下のボタンでチケットを閉じることができます。", color=discord.Color.green())
        await ticket_channel.send(embed=embed, view=close_view)
        await interaction.response.send_message(f"✨ チケットを作成しました: {ticket_channel.mention}", ephemeral=True)

class TicketCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("🔒 5秒後にこのチャンネルを削除します...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

# ⚙️ 11個のボタンを搭載した管理者専用コントロールパネル
class AdminControlPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="1. サーバー情報", style=discord.ButtonStyle.secondary, row=0, custom_id="adm_btn_1")
    async def btn_1(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        g = interaction.guild
        await interaction.response.send_message(f"🏰 **{g.name}**\n• メンバー数: {g.member_count}人\n• 作成日: {g.created_at.strftime('%Y/%m/%d')}", ephemeral=True)

    @discord.ui.button(label="2. ルール確認", style=discord.ButtonStyle.secondary, row=0, custom_id="adm_btn_2")
    async def btn_2(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message(f"📜 **現在のルール:**\n{client.server_rule_text}", ephemeral=True)

    @discord.ui.button(label="3. システム状態", style=discord.ButtonStyle.secondary, row=0, custom_id="adm_btn_3")
    async def btn_3(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message(f"🟢 正常稼働中 / 応答速度: `{round(client.latency * 1000)}ms`", ephemeral=True)

    @discord.ui.button(label="4. メンバー数", style=discord.ButtonStyle.secondary, row=1, custom_id="adm_btn_4")
    async def btn_4(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message(f"👥 現在の総メンバー数: **{interaction.guild.member_count}人**", ephemeral=True)

    @discord.ui.button(label="5. Web認証切替", style=discord.ButtonStyle.primary, row=1, custom_id="adm_btn_5")
    async def btn_5(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        client.web_auth_enabled = not client.web_auth_enabled
        status = "🟢 有効" if client.web_auth_enabled else "🔴 無効"
        await interaction.response.send_message(f"⚙️ Web認証システムを **{status}** に切り替えました。", ephemeral=True)

    @discord.ui.button(label="6. ロール一覧", style=discord.ButtonStyle.secondary, row=1, custom_id="adm_btn_6")
    async def btn_6(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        roles = [r.mention for r in interaction.guild.roles if r != interaction.guild.default_role]
        await interaction.response.send_message(f"🛡️ ロール数: {len(roles)}個", ephemeral=True)

    @discord.ui.button(label="7. 全体アナウンス", style=discord.ButtonStyle.success, row=2, custom_id="adm_btn_7")
    async def btn_7(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message("📢 `/notify` コマンドで全メンバーにアナウンスを送信できます！", ephemeral=True)

    @discord.ui.button(label="8. スローモード", style=discord.ButtonStyle.secondary, row=2, custom_id="adm_btn_8")
    async def btn_8(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message("🐢 `/slowmode [秒数]` でこのチャンネルの低速モードを変更できます。", ephemeral=True)

    @discord.ui.button(label="9. 削除機能案内", style=discord.ButtonStyle.secondary, row=2, custom_id="adm_btn_9")
    async def btn_9(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message("🧹 `/clear [数]` でメッセージをまとめて一括削除できます。", ephemeral=True)

    @discord.ui.button(label="10. ボット情報", style=discord.ButtonStyle.primary, row=3, custom_id="adm_btn_10")
    async def btn_10(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message("🤖 オールインワンDiscord Bot v3.5", ephemeral=True)

    @discord.ui.button(label="11. メンテナンス案内", style=discord.ButtonStyle.danger, row=3, custom_id="adm_btn_11")
    async def btn_11(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者専用です。", ephemeral=True)
        await interaction.response.send_message("🚨 メンテナンスが必要な場合は `/status-change` でプレイ中ステータスを変更してください。", ephemeral=True)


# ==========================================
# 🚀 新規追加された /bump と /up コマンド
# ==========================================

@client.tree.command(name="bump", description="サーバーの宣伝（BUMP）案内を表示する")
async def bump_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚀 サーバーBUMP（宣伝）案内",
        description=(
            f"{interaction.user.mention} さん、ありがとうございます！\n\n"
            "DISBOARDなどの宣伝Botが導入されているサーバーでは、"
            "`/bump` コマンドを入力することでサーバーを掲示板のトップに浮上させることができます。\n\n"
            "💡 *（※このサーバーにDISBOARD等のBotが導入されていない場合は、公式Botを招待してください）*"
        ),
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="up", description="サーバーの評価アップ（UP）案内を表示する")
async def up_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📈 サーバーUP案内",
        description=(
            f"{interaction.user.mention} さん、サーバーの応援ありがとうございます！\n\n"
            "サーバーのランキングサイトや連携Botに対して `/up` などを送信することで、サーバーの評価や順位をアップさせることができます。"
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)


# ==========================================
# その他のコマンド群
# ==========================================

@client.tree.command(name="admin_panel", description="11個の管理ボタンを搭載した管理者専用コントロールパネルを設置する(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def admin_panel_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚙️ 管理者専用コントロールパネル",
        description="このパネルには管理者向けの便利な管理ボタンが **11個** 設置されています。",
        color=discord.Color.dark_red()
    )
    view = AdminControlPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✨ 11個のボタン付き管理者パネルを設置しました。", ephemeral=True)

@client.tree.command(name="ticket_panel", description="サポートチケット作成パネルを設置する(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🎫 サポートチケット", description="下のボタンを押すとあなた専用の問い合わせチャンネルが作成されます。", color=discord.Color.blue())
    view = TicketCreateView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✨ チケットパネルを設置しました。", ephemeral=True)

@client.tree.command(name="dice", description="1〜6のサイコロを振る")
async def dice_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🎲 サイコロの出目: **{random.randint(1, 6)}**")

@client.tree.command(name="slot", description="スロットマシンで遊ぶ")
async def slot_cmd(interaction: discord.Interaction):
    f = ["🍎", "🍊", "🍋", "🍇", "🍓", "🍒", "⭐", "💎"]
    s = [random.choice(f), random.choice(f), random.choice(f)]
    res = "🎉 当たり！" if s[0] == s[1] == s[2] else "💦 ハズレ..."
    await interaction.response.send_message(f"🎰 | {s[0]} | {s[1]} | {s[2]} |\n{res}")

@client.tree.command(name="omikuji", description="今日の運勢を占う")
async def omikuji_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"⛩️ {interaction.user.mention} さんの運勢: **{random.choice(['大吉 🌟', '中吉 ✨', '小吉 🍀', '吉 👍', '凶 💧'])}**")

@client.tree.command(name="coinflip", description="コイントス（表か裏）")
@app_commands.choices(choice=[app_commands.Choice(name="表", value="表"), app_commands.Choice(name="裏", value="裏")])
async def coin_cmd(interaction: discord.Interaction, choice: str):
    res = random.choice(["表", "裏"])
    msg = "🎉 当たり！" if choice == res else "💦 外れ..."
    await interaction.response.send_message(f"🪙 結果: **{res}** ({msg})")

@client.tree.command(name="janken", description="Botとじゃんけん勝負")
@app_commands.choices(hand=[app_commands.Choice(name="グー", value="グー"), app_commands.Choice(name="チョキ", value="チョキ"), app_commands.Choice(name="パー", value="パー")])
async def janken_cmd(interaction: discord.Interaction, hand: str):
    bot_hand = random.choice(["グー", "チョキ", "パー"])
    if hand == bot_hand: res = "あいこ！"
    elif (hand=="グー" and bot_hand=="チョキ") or (hand=="チョキ" and bot_hand=="パー") or (hand=="パー" and bot_hand=="グー"): res = "あなたの勝ち！🎉"
    else: res = "私の勝ち！🤖"
    await interaction.response.send_message(f"あなた: {hand} vs Bot: {bot_hand}\n結果: **{res}**")

@client.tree.command(name="eightball", description="魔法の8ボールに質問する")
async def eightball_cmd(interaction: discord.Interaction, question: str):
    answers = ["確実です", "その通り", "たぶんね", "何とも言えない", "やめておいた方がいい", "絶対にない"]
    await interaction.response.send_message(f"❓ 質問: {question}\n🎱 答え: **{random.choice(answers)}**")

@client.tree.command(name="gacha", description="星5が出るまで引けないガチャを回す")
async def gacha_cmd(interaction: discord.Interaction):
    items = ["★1 雑草", "★2 石ころ", "★3 木の棒", "★4 銅の剣", "🌟 ★5 伝説の聖剣！"]
    await interaction.response.send_message(f"🎁 ガチャ結果: **{random.choice(items)}**")

@client.tree.command(name="luckycolor", description="今日のラッキーカラーを占う")
async def color_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🎨 今日のラッキーカラー: **{random.choice(['赤', '青', '緑', '黄色', '紫', 'ピンク', '黒', '白', 'ゴールド']}**")

@client.tree.command(name="genpass", description="安全なランダムパスワードを生成する")
async def genpass_cmd(interaction: discord.Interaction):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%"
    pwd = "".join(random.choice(chars) for _ in range(12))
    await interaction.response.send_message(f"🔑 生成されたパスワード: `{pwd}`", ephemeral=True)

@client.tree.command(name="choose", description="複数の選択肢から一つランダムに選ぶ")
async def choose_cmd(interaction: discord.Interaction, option1: str, option2: str, option3: str = None):
    opts = [option1, option2]
    if option3: opts.append(option3)
    await interaction.response.send_message(f"🎯 選ばれたのは: **{random.choice(opts)}**")

@client.tree.command(name="servericon", description="サーバーのアイコン画像を表示する")
async def servericon_cmd(interaction: discord.Interaction):
    if interaction.guild.icon:
        await interaction.response.send_message(interaction.guild.icon.url)
    else:
        await interaction.response.send_message("❌ アイコンはありません。", ephemeral=True)

@client.tree.command(name="countchars", description="入力したテキストの文字数を数える")
async def count_cmd(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"📝 文字数: **{len(text)}文字**")

@client.tree.command(name="upper", description="英語を大文字に変換する")
async def upper_cmd(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text.upper())

@client.tree.command(name="lower", description="英語を小文字に変換する")
async def lower_cmd(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text.lower())

@client.tree.command(name="reverse", description="テキストを逆順にする")
async def reverse_cmd(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text[::-1])

@client.tree.command(name="botinfo", description="このBotの情報を表示する")
async def botinfo_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🤖 Bot情報", description="多機能オールインワンDiscord Bot", color=discord.Color.blurple())
    embed.add_field(name="開発者", value="Gemini", inline=True)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="notify", description="メンション付きで全体にお知らせを飛ばす(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def notify_cmd(interaction: discord.Interaction, title: str, content: str):
    embed = discord.Embed(title=f"📢 {title}", description=content, color=discord.Color.red())
    await interaction.channel.send("@everyone", embed=embed)
    await interaction.response.send_message("✨ 通知を送信しました。", ephemeral=True)

@client.tree.command(name="chlink", description="指定したチャンネルへのリンクを生成する")
async def chlink_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.send_message(f"🔗 チャンネルリンク: {channel.mention}")

@client.tree.command(name="randomnum", description="最小値から最大値までのランダムな数値を出す")
async def randnum_cmd(interaction: discord.Interaction, min_val: int, max_val: int):
    if min_val >= max_val:
        return await interaction.response.send_message("❌ 最小値は最大値より小さくしてください。", ephemeral=True)
    await interaction.response.send_message(f"🔢 抽選結果: **{random.randint(min_val, max_val)}**")

@client.tree.command(name="slowmode", description="チャンネルの低速モードを設定する(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def slowmode_cmd(interaction: discord.Interaction, seconds: int):
    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"🐢 低速モードを **{seconds}秒** に設定しました。", ephemeral=True)

@client.tree.command(name="rename", description="現在のチャンネル名を変更する(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def rename_cmd(interaction: discord.Interaction, new_name: str):
    await interaction.channel.edit(name=new_name)
    await interaction.response.send_message(f"✏️ チャンネル名を **{new_name}** に変更しました。", ephemeral=True)

@client.tree.command(name="roles", description="サーバーのロール一覧を表示する")
async def roles_cmd(interaction: discord.Interaction):
    roles = [r.mention for r in interaction.guild.roles if r != interaction.guild.default_role]
    embed = discord.Embed(title="🛡️ ロール一覧", description=", ".join(roles) if roles else "なし", color=discord.Color.orange())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="emojis", description="サーバーの絵文字一覧を表示")
async def emojis_cmd(interaction: discord.Interaction):
    emojis = [str(e) for e in interaction.guild.emojis]
    await interaction.response.send_message(f"😀 **カスタム絵文字:**\n" + ("".join(emojis[:30]) if emojis else "なし"))

@client.tree.command(name="timer", description="指定秒数後にメンションで通知する")
async def timer_cmd(interaction: discord.Interaction, seconds: int):
    if seconds > 300:
        return await interaction.response.send_message("❌ 最大300秒までです。", ephemeral=True)
    await interaction.response.send_message(f"⏱️ **{seconds}秒** のタイマーを開始しました！")
    await asyncio.sleep(seconds)
    await interaction.followup.send(f"⏰ {interaction.user.mention} 時間になりました！")

@client.tree.command(name="luckynumber", description="今日のラッキーナンバーを占う")
async def luckynum_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🔢 今日のラッキーナンバー: **{random.randint(1, 100)}**")

@client.tree.command(name="membercount", description="現在の総メンバー数を確認する")
async def membercount_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"👥 現在のメンバー数: **{interaction.guild.member_count}人**")

@client.tree.command(name="leet", description="テキストをLeet文字に変換する")
async def leet_cmd(interaction: discord.Interaction, text: str):
    table = str.maketrans("aeoglstAEOGLST", "43091574309157")
    await interaction.response.send_message(text.translate(table))

@client.tree.command(name="hello", description="Botが挨拶を返す")
async def hello_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"こんにちは！ {interaction.user.mention} さん、今日も良い一日を！✨")

@client.tree.command(name="acchimuite", description="Botとあっち向いてホイ勝負")
@app_commands.choices(direction=[app_commands.Choice(name="上", value="上"), app_commands.Choice(name="下", value="下"), app_commands.Choice(name="左", value="左"), app_commands.Choice(name="右", value="右")])
async def acchi_cmd(interaction: discord.Interaction, direction: str):
    bot_dir = random.choice(["上", "下", "左", "右"])
    res = "🎉 あなたの勝ち！" if direction == bot_dir else "❌ ざんねん！"
    await interaction.response.send_message(f"あなた: {direction} vs Bot: {bot_dir} → **{res}**")

@client.tree.command(name="weather", description="サーバー内の天気を占う")
async def weather_cmd(interaction: discord.Interaction):
    weathers = ["☀️ 晴れ時々爆笑", "🌧️ 涙の感動ストーリー", "⚡ 雷注意報", "🌈 平和な虹色晴天", "❄️ アイスエイジ"]
    await interaction.response.send_message(f"🌤️ 本日のサーバー天気: **{random.choice(weathers)}**")

@client.tree.command(name="think", description="Botが深く考えるフリをする")
async def think_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🤔 うーん……", ephemeral=True)
    await asyncio.sleep(2)
    await interaction.followup.send(f"💡 {interaction.user.mention} ぴーんときました！「楽しむこと」が一番です！")

@client.tree.command(name="neko", description="かわいい猫の絵文字を飛ばす")
async def neko_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🐾 にゃーん！ 🐈 ＝・ω・＝")

@client.tree.command(name="luckyfood", description="今日のおすすめフードを決める")
async def food_cmd(interaction: discord.Interaction):
    foods = ["ラーメン 🍜", "寿司 🍣", "カレーライス 🍛", "焼肉 🥩", "オムライス 🍳", "ハンバーガー 🍔", "ピザ 🍕", "うどん 🍲"]
    await interaction.response.send_message(f"🍽️ 今日のおすすめフード: **{random.choice(foods)}**")

# 標準コマンド群
@client.tree.command(name="user_status", description="ユーザーの対応可能状態を確認・設定する")
@app_commands.choices(action=[app_commands.Choice(name="確認する", value="get"), app_commands.Choice(name="設定する", value="set")])
@app_commands.choices(status_type=[app_commands.Choice(name="🟢 対応可能", value="対応可能"), app_commands.Choice(name="🔴 取り込み中", value="取り込み中")])
async def user_status_cmd(interaction: discord.Interaction, action: str, target_user: discord.Member = None, status_type: str = None, note: str = "なし"):
    if action == "set":
        client.user_availability_status[interaction.user.id] = {"status": status_type, "note": note}
        await interaction.response.send_message(f"✨ ステータスを **[{status_type}]** に設定しました！", ephemeral=True)
    else:
        target = target_user or interaction.user
        data = client.user_availability_status.get(target.id, {"status": "未設定", "note": "なし"})
        await interaction.response.send_message(f"🎧 {target.display_name} のステータス: **{data['status']}** (`{data['note']}`)", ephemeral=True)

@client.tree.command(name="rikkouho", description="開催中の選挙に立候補する")
async def rikkouho_cmd(interaction: discord.Interaction, election_message_id: str, candidate_name: str, pr_text: str):
    try:
        msg_id = int(election_message_id)
    except ValueError:
        return await interaction.response.send_message("❌ IDは半角数字で入力してください。", ephemeral=True)
    if msg_id not in client.election_candidates:
        client.election_candidates[msg_id] = []
    client.election_candidates[msg_id].append({"user_id": interaction.user.id, "name": candidate_name, "pr": pr_text})
    await interaction.response.send_message(f"✨ 選挙（ID: `{msg_id}`）への立候補を受け付けました！", ephemeral=True)

@client.tree.command(name="status", description="Botの稼働状況を表示")
async def status_cmd(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    embed = discord.Embed(title="🟢 稼働状況", description=f"Ping: `{latency}ms` / サーバー数: `{len(client.guilds)}`", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="server", description="サーバー情報を表示")
async def server_info_cmd(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"🏰 {guild.name}", color=discord.Color.blue())
    embed.add_field(name="メンバー数", value=f"{guild.member_count}人", inline=True)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="poll", description="簡易アンケート作成")
async def poll_cmd(interaction: discord.Interaction, question: str, option1: str, option2: str):
    msg = await interaction.channel.send(embed=discord.Embed(title="📊 アンケート", description=f"Q. {question}\n\n1️⃣ {option1}\n2️⃣ {option2}", color=discord.Color.blurple()))
    await msg.add_reaction("1️⃣")
    await msg.add_reaction("2️⃣")
    await interaction.response.send_message("✨ アンケートを作成しました！", ephemeral=True)

@client.tree.command(name="clear", description="メッセージ一括削除(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def clear_cmd(interaction: discord.Interaction, count: int):
    deleted = await interaction.channel.purge(limit=count)
    await interaction.response.send_message(f"🗑️ {len(deleted)}件削除しました。", ephemeral=True)

@client.tree.command(name="userinfo", description="ユーザー情報表示")
async def userinfo_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.send_message(f"👤 ユーザー: **{target.display_name}** (ID: `{target.id}`)", ephemeral=True)

@client.tree.command(name="help", description="使い方を表示")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("📖 `/admin_panel` から11個の管理ボタンを設置できます！", ephemeral=True)

# 起動
token = os.environ.get("DISCORD_TOKEN")
if token:
    client.run(token)
else:
    print("Error: DISCORD_TOKEN environment variable is not set.")
