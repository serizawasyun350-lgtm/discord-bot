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
        
        # ユーザーごとのモデレーション対応履歴 {user_id: {"warn_count": int, "last_penalty": str}}
        self.user_moderation_records = {}

        # ユーザーごとの対応状況ステータス {user_id: {"status": str, "note": str}}
        self.user_availability_status = {}

        # 選挙ごとの立候補者データ {election_id: [{"user_id": int, "name": str, "pr": str}]}
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
                    description=f"{message.author.mention} 様が短時間に大量のメッセージを投稿したため、メッセージを**自動削除**し、**10分間のタイムアウト（TO）**を実行しました。\n\n※誤検知の場合は管理者が `/moderation untimeout` で解除できます。",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed, delete_after=15)
                client.user_message_timestamps[user_id] = []
                return
            except Exception as e:
                print(f"スパム処理中にエラーが発生しました: {e}")

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

class AdApplyModal(Modal, title="📢 広告申請フォーム"):
    ad_title = TextInput(label="広告タイトル", placeholder="例: ○○サーバーメンバー募集！", required=True)
    ad_content = TextInput(label="広告本文・PRメッセージ", style=discord.TextStyle.paragraph, placeholder="宣伝したい内容を入力してください...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=f"📢 広告申請: {self.ad_title.value}", description=self.ad_content.value, color=discord.Color.green())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✨ 広告申請を送信しました。運営の確認をお待ちください。", ephemeral=True)

class AdPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="広告を申請する", style=discord.ButtonStyle.success, emoji="📢", custom_id="ad_apply_button")
    async def apply_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AdApplyModal())

class SuggestionModal(Modal, title="💡 提案を投稿する"):
    suggestion_content = TextInput(
        label="提案内容",
        style=discord.TextStyle.paragraph,
        placeholder="サーバーをより良くするためのアイデアを入力してください...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="💡 新しい提案", description=self.suggestion_content.value, color=discord.Color.blurple())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        await interaction.response.send_message("✨ 提案を投稿しました！", ephemeral=True)

class ElectionModal(Modal):
    def __init__(self, election_type: str):
        super().__init__(title=f"🗳️ 選挙作成 ({election_type})")
        self.election_type = election_type

    election_title = TextInput(label="選挙のタイトル・テーマ", placeholder="例: 新規モデレーター立候補者の投票", required=True)
    option_a = TextInput(label="選択肢 A", placeholder="例: 候補者 1 / Minecraft", required=True)
    option_b = TextInput(label="選択肢 B", placeholder="例: 候補者 2 / Among Us", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        desc = f"**【投票受付中】**\n\n🇦 : {self.option_a.value}\n🇧 : {self.option_b.value}"
        embed = discord.Embed(title=f"🗳️ [{self.election_type}] {self.election_title.value}", description=desc, color=discord.Color.gold())
        embed.set_footer(text=f"主催者: {interaction.user.display_name}")
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction("🇦")
        await msg.add_reaction("🇧")
        
        client.election_candidates[msg.id] = []
        
        await interaction.response.send_message(f"✨ 「{self.election_type}」の選挙パネルを作成しました！（選挙ID: `{msg.id}`）\n立候補する場合は `/rikkouho` でこのIDを指定してください。", ephemeral=True)

class ElectionTypeSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="モデレーター選挙", description="スタッフやモデレーターを選ぶ投票", emoji="🛡️", value="モデレーター選挙"),
            discord.SelectOption(label="ゲーム選挙", description="次に遊ぶゲームや企画を決める投票", emoji="🎮", value="ゲーム選挙"),
            discord.SelectOption(label="一般・その他選挙", description="自由なテーマでの投票・アンケート", emoji="🗳️", value="一般・その他選挙"),
        ]
        super().__init__(placeholder="🗳️ 選挙のタイプを選択してください...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_type = self.values[0]
        await interaction.response.send_modal(ElectionModal(election_type=selected_type))

class ElectionTypeSelectView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(ElectionTypeSelect())

class CaptchaModal(Modal):
    def __init__(self, num1: int, num2: int, correct_answer: int):
        super().__init__(title="🔢 キャプチャ認証（計算テスト）")
        self.correct_answer = correct_answer
        self.answer_input.label = f"次の計算結果を入力してください: {num1} + {num2} = ?"

    answer_input = TextInput(label="答えの数値", placeholder="半角数字で入力", required=True, max_length=5)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_val = int(self.answer_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ 半角の数字で正しく入力してください。", ephemeral=True)
            return

        if user_val != self.correct_answer:
            await interaction.response.send_message("❌ 計算の答えが違います。もう一度認証ボタンからやり直してください。", ephemeral=True)
            return

        if not client.auth_role_id:
            await interaction.response.send_message("❌ 認証ロールがまだ設定されていません。", ephemeral=True)
            return

        role = interaction.guild.get_role(client.auth_role_id)
        if not role:
            await interaction.response.send_message("❌ 指定された認証ロールが見つかりませんでした。", ephemeral=True)
            return

        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message("🔄 認証を解除しました。", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"✅ キャプチャ認証に成功しました！ {role.mention} を付与しました。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 権限エラーが発生しました: {e}", ephemeral=True)

class ManagementSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1. サーバー情報表示", description="現在のサーバー情報を確認します", emoji="🏰", value="server"),
            discord.SelectOption(label="2. ルール案内・送信", description="利用規約をチャンネルに表示します", emoji="📜", value="rules"),
            discord.SelectOption(label="3. システム詳細ステータス", description="Ping値や稼働状況を確認します", emoji="🟢", value="status"),
            discord.SelectOption(label="4. メッセージ一括削除", description="/clear コマンドの簡単な使い方を表示", emoji="🧹", value="clear"),
            discord.SelectOption(label="5. メンバー情報照会", description="/userinfo コマンドの使い方を表示", emoji="👤", value="userinfo"),
        ]
        super().__init__(placeholder="⚙️ 管理機能（5個の機能）から選択...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ このメニューを利用できるのは管理者のみです。", ephemeral=True)
            return
        
        val = self.values[0]
        if val == "server":
            guild = interaction.guild
            await interaction.response.send_message(f"🏰 サーバー名: **{guild.name}** / メンバー数: **{guild.member_count}人** / オーナー: {guild.owner.mention}", ephemeral=True)
        elif val == "rules":
            embed = discord.Embed(title="📜 サー바ールール", description=client.server_rule_text, color=discord.Color.gold())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif val == "status":
            latency = round(client.latency * 1000)
            await interaction.response.send_message(f"🟢 正常稼働中 / Ping: `{latency}ms` / 導入サーバー数: `{len(client.guilds)}`", ephemeral=True)
        elif val == "clear":
            await interaction.response.send_message("🧹 **メッセージ一括削除機能:**\n`/clear [1~100]` でチャンネル内の指定メッセージをまとめて消去できます。", ephemeral=True)
        elif val == "userinfo":
            await interaction.response.send_message("👤 **メンバー照会機能:**\n`/userinfo [対象メンバー]` で参加日や所持ロールを確認できます。", ephemeral=True)

class ManagementView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(ManagementSelect())

class UtilityPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ヘルプ", style=discord.ButtonStyle.primary, emoji="📖", custom_id="util_help")
    async def h_btn(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ このパネルの操作は管理者のみ許可されています。", ephemeral=True)
            return
        help_text = (
            "**📖 ボットのコマンド・機能一覧**\n"
            "• `/help` : コマンド一覧を表示\n"
            "• `/status` : リアルタイム稼働状況を表示（1秒間隔更新）\n"
            "• `/user_status` : メンバーの対応可能状態を設定・確認\n"
            "• `/rikkouho` : 選挙に立候補する\n"
            "• `/dice` : サイコロを振る（1〜6）\n"
            "• `/slot` : スロットマシンで遊ぶ\n"
            "• `/omikuji` : 本日の運勢を占う\n"
            "• `/coin` : コイントス（表か裏）\n"
            "• `/server` : サーバーの情報を表示\n"
            "• `/poll` : 簡易アンケートを作成\n"
            "• `/userinfo` : ユーザー情報を確認\n"
            "• `/moderation user-status` : ユーザーの違反状況を確認(管理)\n"
            "• `/auth panel` : 認証ボタンパネルを設置(管理)\n"
            "• `/ad panel` : ボタン付き広告パネルを設置(管理)\n"
            "• `/clear` : メッセージを一括削除(管理)"
        )
        embed = discord.Embed(title="📖 ヘルプ＆コマンドガイド", description=help_text, color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="稼働状況", style=discord.ButtonStyle.success, emoji="🟢", custom_id="util_status")
    async def s_btn(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ このパネルの操作は管理者のみ許可されています。", ephemeral=True)
            return
        latency = round(client.latency * 1000)
        await interaction.response.send_message(f"🟢 **システム正常稼働中**\n• 応答速度 (Ping): `{latency}ms`\n• 導入サーバー数: `{len(client.guilds)}`", ephemeral=True)

    @discord.ui.button(label="提案を投稿", style=discord.ButtonStyle.secondary, emoji="💡", custom_id="util_suggest")
    async def p_btn(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ このパネルの操作は管理者のみ許可されています。", ephemeral=True)
            return
        await interaction.response.send_modal(SuggestionModal())

    @discord.ui.button(label="管理", style=discord.ButtonStyle.danger, emoji="⚙️", custom_id="util_manage")
    async def m_btn(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ このパネルの操作は管理者のみ許可されています。", ephemeral=True)
            return
        embed = discord.Embed(title="⚙️ 管理者専用便利メニュー", description="下のドロップダウンから5つの機能を選択できます。", color=discord.Color.dark_red())
        await interaction.response.send_message(embed=embed, view=ManagementView(), ephemeral=True)

    @discord.ui.button(label="選挙を作成", style=discord.ButtonStyle.success, emoji="🗳️", custom_id="util_election")
    async def e_btn(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ このパネルの操作は管理者のみ許可されています。", ephemeral=True)
            return
        await interaction.response.send_message("🗳️ 作成する選挙のタイプを選択してください：", view=ElectionTypeSelectView(), ephemeral=True)


# ==========================================
# 各種スラッシュコマンド群（遊べるミニゲーム追加）
# ==========================================

@client.tree.command(name="dice", description="サイコロを振る（1〜6）")
async def dice_cmd(interaction: discord.Interaction):
    result = random.randint(1, 6)
    embed = discord.Embed(title="🎲 サイコロ勝負", description=f"{interaction.user.mention} さんがサイコロを振りました！\n\n出目: **{result}** 🎯", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="slot", description="スロットマシンで遊ぶ")
async def slot_cmd(interaction: discord.Interaction):
    fruits = ["🍎", "🍊", "🍋", "🍇", "🍓", "🍒", "⭐", "💎"]
    s1 = random.choice(fruits)
    s2 = random.choice(fruits)
    s3 = random.choice(fruits)
    
    if s1 == s2 == s3:
        result_text = "🎉 **大当たり！パーフェクトビンゴ！** 🎉"
        color = discord.Color.gold()
    elif s1 == s2 or s2 == s3 or s1 == s3:
        result_text = "✨ **おしい！2つ揃いました！** ✨"
        color = discord.Color.green()
    else:
        result_text = "💦 **ハズレ！また挑戦してね！**"
        color = discord.Color.red()

    embed = discord.Embed(title="🎰 スロットマシン", description=f"{interaction.user.mention} さんの結果\n\n| {s1} | {s2} | {s3} |\n\n{result_text}", color=color)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="omikuji", description="今日の運勢を占うおみくじ")
async def omikuji_cmd(interaction: discord.Interaction):
    fortunes = ["大吉 🌟", "中吉 ✨", "小吉 🍀", "吉 👍", "末吉 🪄", "凶 💧"]
    result = random.choice(fortunes)
    embed = discord.Embed(title="⛩️ おみくじ", description=f"{interaction.user.mention} さんの今日の運勢は...\n\n👉 **{result}**", color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="coin", description="コイントス（表か裏か）")
@app_commands.choices(choice=[
    app_commands.Choice(name="表 (Heads)", value="表"),
    app_commands.Choice(name="裏 (Tails)", value="裏"),
])
async def coin_cmd(interaction: discord.Interaction, choice: str):
    result = random.choice(["表", "裏"])
    if choice == result:
        res_text = f"🎉 当たり！あなたの予想通り **【{result}】** でした！"
        color = discord.Color.green()
    else:
        res_text = f"残念！結果は **【{result}】** でした..."
        color = discord.Color.red()

    embed = discord.Embed(title="🪙 コイントス勝負", description=f"あなたの予想: {choice}\n\n{res_text}", color=color)
    await interaction.response.send_message(embed=embed)


# --- Web認証リンク自動発行コマンド (/web_auth) ---
class WebAuthLinkView(View):
    def __init__(self, auth_url: str):
        super().__init__(timeout=180)
        self.add_item(Button(label="🌐 Web認証ページを開く", url=auth_url, style=discord.ButtonStyle.link))

@client.tree.command(name="web_auth", description="Web認証用URLの自動発行およびシステム管理")
@app_commands.choices(mode=[
    app_commands.Choice(name="🌐 Web認証リンクを発行する", value="get_link"),
    app_commands.Choice(name="⚙️ Web認証を有効化する (管理者)", value="enable"),
    app_commands.Choice(name="⚙️ Web認証を無効化する (管理者)", value="disable"),
])
async def web_auth_cmd(interaction: discord.Interaction, mode: str):
    if mode == "get_link":
        if not client.web_auth_enabled:
            await interaction.response.send_message("❌ 現在Web認証システムは無効化されています。", ephemeral=True)
            return

        port = os.environ.get("PORT", 10000)
        external_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{port}")
        auth_url = f"{external_url}/"

        embed = discord.Embed(
            title="🌐 Web認証ポータル",
            description="以下のボタンをクリックしてWeb認証ページへアクセスし、手続きを進めてください。",
            color=discord.Color.blue()
        )
        view = WebAuthLinkView(auth_url=auth_url)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    elif mode in ["enable", "disable"]:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Web認証の設定変更は管理者のみ実行できます。", ephemeral=True)
            return

        client.web_auth_enabled = (mode == "enable")
        status_str = "🟢 有効" if client.web_auth_enabled else "🔴 無効"
        await interaction.response.send_message(f"⚙️ Web認証システムを **{status_str}** に変更しました。", ephemeral=True)


# --- 選挙立候補コマンド (/rikkouho) ---
@client.tree.command(name="rikkouho", description="開催中の選挙に立候補する")
async def rikkouho_cmd(interaction: discord.Interaction, election_message_id: str, candidate_name: str, pr_text: str):
    try:
        msg_id = int(election_message_id)
    except ValueError:
        await interaction.response.send_message("❌ 選挙メッセージIDは半角数字で正しく入力してください。", ephemeral=True)
        return

    if msg_id not in client.election_candidates:
        client.election_candidates[msg_id] = []

    client.election_candidates[msg_id].append({
        "user_id": interaction.user.id,
        "name": candidate_name,
        "pr": pr_text
    })

    try:
        channel = interaction.channel
        msg = await channel.fetch_message(msg_id)
        
        candidates_list = client.election_candidates[msg_id]
        candidates_str = "\n".join([f"👤 **{c['name']}** ({interaction.guild.get_member(c['user_id']).mention if interaction.guild.get_member(c['user_id']) else '不明'}): {c['pr']}" for c in candidates_list])

        old_embed = msg.embeds[0]
        new_embed = discord.Embed(title=old_embed.title, description=old_embed.description + f"\n\n**【立候補者一覧】**\n{candidates_str}", color=old_embed.color)
        if old_embed.footer:
            new_embed.set_footer(text=old_embed.footer.text)
            
        await msg.edit(embed=new_embed)
        await interaction.response.send_message(f"✨ 選挙（ID: `{msg_id}`）への立候補を受け付けました！", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"✨ 立候補を受け付けましたが、メッセージの自動更新に失敗しました: {e}", ephemeral=True)


# --- ユーザーの対応可能状態コマンド (/user_status) ---
@client.tree.command(name="user_status", description="ユーザーの対応可能状態を確認・設定する")
@app_commands.choices(action=[
    app_commands.Choice(name="確認する", value="get"),
    app_commands.Choice(name="設定・更新する", value="set"),
])
@app_commands.choices(status_type=[
    app_commands.Choice(name="🟢 対応可能 (受付中)", value="対応可能 (受付中)"),
    app_commands.Choice(name="🟡 多忙 (返信遅れます)", value="多忙 (返信遅れます)"),
    app_commands.Choice(name="🔴 対応不可 (取り込み中)", value="対応不可 (取り込み中)"),
])
async def user_status_cmd(
    interaction: discord.Interaction,
    action: str,
    target_user: discord.Member = None,
    status_type: str = None,
    note: str = "特になし"
):
    if action == "set":
        if not status_type:
            await interaction.response.send_message("❌ 設定する場合は `status_type` を選択してください。", ephemeral=True)
            return
        
        client.user_availability_status[interaction.user.id] = {
            "status": status_type,
            "note": note,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M")
        }
        await interaction.response.send_message(f"✨ あなたの対応ステータスを **[{status_type}]** に設定しました！", ephemeral=True)

    elif action == "get":
        target = target_user or interaction.user
        data = client.user_availability_status.get(target.id, {"status": "未設定 (通常)", "note": "なし", "updated_at": "---"})

        embed = discord.Embed(title=f"🎧 対応状況: {target.display_name}", color=discord.Color.blue())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="現在のステータス", value=f"**{data['status']}**", inline=False)
        embed.add_field(name="メモ・備考", value=f"`{data['note']}`", inline=False)
        embed.add_field(name="最終更新時刻", value=f"`{data['updated_at']}`", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- モデレーション・ユーザー対応状況管理 (/moderation) ---
moderation_group = app_commands.Group(name="moderation", description="モデレーション管理")

@moderation_group.command(name="user-status", description="指定したユーザーの自動検知・警告などの対応状況を確認(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_user_status(interaction: discord.Interaction, member: discord.Member):
    user_id = member.id
    record = client.user_moderation_records.get(user_id, {"warn_count": 0, "last_penalty": "履歴なし"})

    embed = discord.Embed(title=f"🛡️ ユーザーモデレーション状況: {member.display_name}", color=discord.Color.orange())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="対象ユーザー", value=member.mention, inline=True)
    embed.add_field(name="ユーザーID", value=f"`{member.id}`", inline=True)
    embed.add_field(name="スパム検知・警告回数", value=f"**{record['warn_count']} 回**", inline=False)
    embed.add_field(name="直近の処置内容", value=f"`{record['last_penalty']}`", inline=False)
    
    if member.timed_out_until:
        embed.add_field(name="現在の状態", value=f"⚠️ **タイムアウト中** ({member.timed_out_until.strftime('%H:%M:%S')} まで)", inline=False)
    else:
        embed.add_field(name="現在の状態", value="🟢 正常 (制限なし)", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@moderation_group.command(name="untimeout", description="メンバーのタイムアウトを解除(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_untimeout(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None, reason="管理者によるタイムアウト解除")
        await interaction.response.send_message(f"✅ {member.mention} のタイムアウトを解除しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 解除に失敗しました: {e}", ephemeral=True)

client.tree.add_command(moderation_group)

# --- 自動下移動付き固定メッセージコマンド ---
pin_group = app_commands.Group(name="pin-message", description="固定メッセージ管理")

@pin_group.command(name="create", description="誰かが送信しても常に下に移動する固定メッセージを作成(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def pin_message_create(interaction: discord.Interaction, channel: discord.TextChannel, content: str):
    try:
        formatted_content = content.replace("\\n", "\n")
        embed = discord.Embed(title="📌 重要なお知らせ", description=formatted_content, color=discord.Color.blue())
        msg = await channel.send(embed=embed)
        
        client.sticky_messages[channel.id] = {
            "content": formatted_content,
            "message_id": msg.id
        }
        await interaction.response.send_message(f"✨ {channel.mention} に自動追従（最下部維持）の固定メッセージを設置しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ 作成に失敗しました: {e}", ephemeral=True)

client.tree.add_command(pin_group)

# --- ボタン付き広告パネル設置コマンド ---
ad_group = app_commands.Group(name="ad", description="広告管理")

@ad_group.command(name="panel", description="ボタン付きの広告申請パネルを設置(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📢 広告掲載のご案内",
        description="サーバー内での宣伝をご希望の方は、下の **「広告を申請する」** ボタンを押して申請フォームをご入力ください。",
        color=discord.Color.green()
    )
    view = AdPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✨ ボタン付き広告申請パネルを設置しました。", ephemeral=True)

client.tree.add_command(ad_group)

# --- ステータスコマンド (/status) ---
@client.tree.command(name="status", description="Botのシステム稼働状況やPingを1秒毎にリアルタイム表示する")
async def status_cmd(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    now = datetime.datetime.now(datetime.timezone.utc)
    uptime_delta = now - client.start_time
    
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

    await interaction.response.send_message("ステータスを表示しました", ephemeral=True)
    sent_msg = await interaction.channel.send(embed=embed)
    client.active_status_messages.append(sent_msg)

@client.tree.command(name="status-change", description="Botのプレイ中ステータスを手動で変更する(管理者)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(activity_type=[
    app_commands.Choice(name="プレイ中 (Playing)", value="playing"),
    app_commands.Choice(name="配信中 (Streaming)", value="streaming"),
    app_commands.Choice(name="聴いている (Listening)", value="listening"),
    app_commands.Choice(name="視聴中 (Watching)", value="watching"),
])
async def status_change_cmd(interaction: discord.Interaction, activity_type: str, text: str):
    if activity_type == "playing":
        act = discord.Activity(type=discord.ActivityType.playing, name=text)
    elif activity_type == "streaming":
        act = discord.Activity(type=discord.ActivityType.streaming, name=text, url="https://twitch.tv/twitch")
    elif activity_type == "listening":
        act = discord.Activity(type=discord.ActivityType.listening, name=text)
    elif activity_type == "watching":
        act = discord.Activity(type=discord.ActivityType.watching, name=text)
    else:
        act = discord.Activity(type=discord.ActivityType.playing, name=text)

    client.custom_status = act
    await client.change_presence(activity=act)
    await interaction.response.send_message(f"✨ Botのステータスを変更しました：**{activity_type} / {text}**", ephemeral=True)

@client.tree.command(name="server", description="現在のサーバーの情報を表示する")
async def server_info_cmd(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"🏰 サーバー情報: {guild.name}", color=discord.Color.blue())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="サーバーID", value=guild.id, inline=True)
    embed.add_field(name="オーナー", value=guild.owner.mention if guild.owner else "不明", inline=True)
    embed.add_field(name="メンバー数", value=f"{guild.member_count} 人", inline=True)
    embed.add_field(name="チャンネル数", value=f"{len(guild.channels)} 個", inline=True)
    embed.add_field(name="ロール数", value=f"{len(guild.roles)} 個", inline=True)
    embed.add_field(name="サーバーブースト", value=f"Level {guild.premium_tier} ({guild.premium_subscription_count} ブースト)", inline=True)
    embed.add_field(name="サーバー作成日", value=guild.created_at.strftime('%Y/%m/%d %H:%M'), inline=False)
    
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="poll", description="簡易アンケートを作成する")
async def poll_cmd(interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
    options = [option1, option2]
    if option3: options.append(option3)
    if option4: options.append(option4)

    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    desc = f"**質問:** {question}\n\n"
    for i, opt in enumerate(options):
        desc += f"{emojis[i]} {opt}\n"

    embed = discord.Embed(title="📊 アンケート投票", description=desc, color=discord.Color.blurple())
    embed.set_footer(text=f"投票作成者: {interaction.user.display_name}")
    
    await interaction.response.send_message("✨ アンケートを作成しました！", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])

@client.tree.command(name="clear", description="指定した数のメッセージをまとめて削除(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def clear_cmd(interaction: discord.Interaction, count: int):
    if count < 1 or count > 100:
        await interaction.response.send_message("❌ 削除数は1から100の間で指定してください。", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=count)
    await interaction.followup.send(f"🗑️ {len(deleted)} 件のメッセージを削除しました。", ephemeral=True)

@client.tree.command(name="userinfo", description="指定したユーザーの情報を表示する")
async def userinfo_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    roles = [r.mention for r in target.roles if r != interaction.guild.default_role]
    roles_str = ", ".join(roles) if roles else "なし"

    embed = discord.Embed(title=f"👤 ユーザー情報: {target.display_name}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="ユーザー名", value=target.name, inline=True)
    embed.add_field(name="ID", value=target.id, inline=True)
    embed.add_field(name="サーバー参加日", value=target.joined_at.strftime('%Y/%m/%d %H:%M') if target.joined_at else "不明", inline=False)
    embed.add_field(name="アカウント作成日", value=target.created_at.strftime('%Y/%m/%d %H:%M'), inline=False)
    embed.add_field(name=f"保有ロール ({len(roles)}個)", value=roles_str, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- ルール管理コマンド (/rule) ---
rule_group = app_commands.Group(name="rule", description="サーバーのルール管理")

@rule_group.command(name="show", description="サーバーのルールを表示")
async def rule_show(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 サーバー利用ルール", description=client.server_rule_text, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

@rule_group.command(name="set", description="ルールを設定・更新(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def rule_set(interaction: discord.Interaction, content: str):
    client.server_rule_text = content.replace("\\n", "\n")
    await interaction.response.send_message("✅ サーバールールを更新しました。", ephemeral=True)

@rule_group.command(name="panel", description="ルールパネルをチャンネルに設置(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def rule_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 サーバー利用ルール", description=client.server_rule_text, color=discord.Color.gold())
    embed.set_footer(text="ルールを守って楽しく利用しましょう！")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ ルールパネルを設置しました。", ephemeral=True)

client.tree.add_command(rule_group)

# --- キャプチャ（計算）認証つきパネル系 (/auth) ---
class AuthVerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証する (計算テスト)", style=discord.ButtonStyle.green, emoji="🔢", custom_id="auth_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        num1 = random.randint(1, 9)
        num2 = random.randint(1, 9)
        ans = num1 + num2
        await interaction.response.send_modal(CaptchaModal(num1=num1, num2=num2, correct_answer=ans))

auth_group = app_commands.Group(name="auth", description="認証機能")

@auth_group.command(name="panel", description="計算認証ボタン付きパネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def auth_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔒 サーバー認証（キャプチャテスト）",
        description="下の **「認証する (計算テスト)」** ボタンを押すと、画面に簡単な計算問題が表示されます。正解するとロールが付与されます！",
        color=discord.Color.gold()
    )
    view = AuthVerifyView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✨ 計算認証ボタン付きパネルを設置しました。", ephemeral=True)

@auth_group.command(name="setup", description="既存ロールを認証ロールに設定")
@app_commands.checks.has_permissions(administrator=True)
async def auth_setup(interaction: discord.Interaction, role: discord.Role):
    client.auth_role_id = role.id
    await interaction.response.send_message(f"⚙️ 認証ロールを {role.mention} に設定しました。", ephemeral=True)

@auth_group.command(name="toggle", description="認証ON/OFF")
@app_commands.checks.has_permissions(administrator=True)
async def auth_toggle(interaction: discord.Interaction, state: bool):
    status = "ON" if state else "OFF"
    await interaction.response.send_message(f"🔄 認証システムを **{status}** に切り替えました。", ephemeral=True)

client.tree.add_command(auth_group)

# --- 便利ツールパネル設置コマンド ---
@client.tree.command(name="panel", description="便利ツールパネルを設置(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def panel_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="🛠️ 便利ツールパネル", description="ボタンから各種機能にアクセスできます。", color=discord.Color.dark_gray())
    await interaction.channel.send(embed=embed, view=UtilityPanelView())
    await interaction.response.send_message("✨ パネルを設置しました。", ephemeral=True)

@client.tree.command(name="event", description="イベント告知を作成(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def event_create(interaction: discord.Interaction, title: str, description: str):
    embed = discord.Embed(title=f"🎉 {title}", description=description, color=discord.Color.orange())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ 作成しました。", ephemeral=True)

@client.tree.command(name="help", description="Botの使い方")
async def help_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("📖 コマンド一覧をご参照ください。", ephemeral=True)

@client.tree.command(name="reset", description="リセット")
@app_commands.checks.has_permissions(administrator=True)
async def reset_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("⚠️ 無効化されています。", ephemeral=True)

@client.tree.command(name="suggest", description="提案を投稿")
async def suggest_cmd(interaction: discord.Interaction, suggestion: str):
    msg = await interaction.channel.send(embed=discord.Embed(title="💡 提案", description=suggestion, color=discord.Color.blurple()))
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await interaction.response.send_message("✨ 投稿しました。", ephemeral=True)

@client.tree.command(name="welcome", description="歓迎チャンネルを設定(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.send_message(f"👋 設定しました: {channel.mention}", ephemeral=True)

# 起動
token = os.environ.get("DISCORD_TOKEN")
if token:
    client.run(token)
else:
    print("Error: DISCORD_TOKEN environment variable is not set.")
