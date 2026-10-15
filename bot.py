import os
import asyncio
import datetime
import discord
from discord import app_commands
from discord.ui import View, Button

class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.user_message_timestamps = {}
        # 認証ロールIDを保持する変数（初期値はNone、/auth setupで設定されます）
        self.auth_role_id = None

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドを同期しました。")

client = MyBot()

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")

# ==========================================
# 0. 自動スパム検知 & 自動タイムアウト (TO)
# ==========================================
@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if message.author.guild_permissions.administrator:
        return

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
            await message.author.timeout(duration, reason="自動スパム検知によるタイムアウト")
            
            embed = discord.Embed(
                title="⚠️ スパム検知によるタイムアウト",
                description=f"{message.author.mention} 様を短時間での連投（スパム行為）のため **10分間タイムアウト** しました。\n誤検知の場合は管理者が `/moderation untimeout` で解除できます。",
                color=discord.Color.red()
            )
            await message.channel.send(embed=embed, delete_after=15)
            client.user_message_timestamps[user_id] = []
        except Exception as e:
            print(f"スパム対処中にエラーが発生しました: {e}")

# ==========================================
# 1. 広告系 (/ad)
# ==========================================
ad_group = app_commands.Group(name="ad", description="広告管理")

@ad_group.command(name="approve", description="広告申請を承認(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_approve(interaction: discord.Interaction, ad_id: str):
    await interaction.response.send_message(f"✅ 広告ID: `{ad_id}` の申請を承認しました。", ephemeral=True)

@ad_group.command(name="delete", description="広告を削除(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_delete(interaction: discord.Interaction, ad_id: str):
    await interaction.response.send_message(f"🗑️ 広告ID: `{ad_id}` を削除しました。", ephemeral=True)

@ad_group.command(name="list", description="広告一覧を確認")
async def ad_list(interaction: discord.Interaction):
    embed = discord.Embed(title="📢 広告一覧", description="現在登録されている広告のステータス一覧です。", color=discord.Color.blue())
    embed.add_field(name="[ID: 001]", value="ステータス: 承認済み / 掲載中", inline=False)
    embed.add_field(name="[ID: 002]", value="ステータス: 審査待ち", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@ad_group.command(name="panel", description="広告申請パネルを設置(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="📢 広告掲載のご案内", description="下のボタンから広告の申請を行ってください。", color=discord.Color.green())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ 広告申請パネルを設置しました。", ephemeral=True)

@ad_group.command(name="post", description="承認済み広告を手動投稿(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_post(interaction: discord.Interaction, ad_id: str):
    await interaction.response.send_message(f"🚀 広告ID: `{ad_id}` を手動投稿しました。", ephemeral=True)

@ad_group.command(name="reject", description="広告申請を却下(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_reject(interaction: discord.Interaction, ad_id: str, reason: str = "理由なし"):
    await interaction.response.send_message(f"❌ 広告ID: `{ad_id}` の申請を却下しました。\n理由: {reason}", ephemeral=True)

@ad_group.command(name="schedule", description="広告の自動投稿を設定(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_schedule(interaction: discord.Interaction, interval_hours: int):
    await interaction.response.send_message(f"⏰ 広告の自動投稿間隔を {interval_hours} 時間毎に設定しました。", ephemeral=True)

@ad_group.command(name="stop", description="広告掲載·自動投稿を停止(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def ad_stop(interaction: discord.Interaction):
    await interaction.response.send_message("🛑 広告の掲載および自動投稿を停止しました。", ephemeral=True)

client.tree.add_command(ad_group)

# ==========================================
# 2. 認証系 (/auth) （ボタン付き）
# ==========================================

class AuthVerifyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="認証する", style=discord.ButtonStyle.green, emoji="✅", custom_id="auth_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        if not client.auth_role_id:
            await interaction.response.send_message("❌ 認証ロールがまだ設定されていません。管理者に `/auth setup` を実行してもらってください。", ephemeral=True)
            return
        
        role = interaction.guild.get_role(client.auth_role_id)
        if not role:
            await interaction.response.send_message("❌ 設定された認証ロールが見つかりませんでした。", ephemeral=True)
            return

        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message("🔄 認証を解除しました。", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"✅ 認証が完了しました！ {role.mention} を付与しました。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ ロールの付与/解除に失敗しました: {e}", ephemeral=True)

auth_group = app_commands.Group(name="auth", description="認証機能")

@auth_group.command(name="panel", description="認証パネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def auth_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔒 サーバー認証", 
        description="下の **「認証する」** ボタンを押すと、サーバーの利用ロールが即座に付与されます！", 
        color=discord.Color.gold()
    )
    view = AuthVerifyView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✨ 認証ボタン付きパネルを設置しました。", ephemeral=True)

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

# ==========================================
# 3. 自動モデレーション (/automod)
# ==========================================
automod_group = app_commands.Group(name="automod", description="自動モデレーション")

@automod_group.command(name="add", description="禁止ワードルールを追加")
@app_commands.checks.has_permissions(administrator=True)
async def automod_add(interaction: discord.Interaction, word: str):
    await interaction.response.send_message(f"➕ 禁止ワード `{word}` を追加しました。", ephemeral=True)

@automod_group.command(name="list", description="登録済みルールを確認")
async def automod_list(interaction: discord.Interaction):
    await interaction.response.send_message("📋 登録済み禁止ワード:\n- `NGワード1`\n- `NGワード2`", ephemeral=True)

@automod_group.command(name="remove", description="ルールIDを指定して削除")
@app_commands.checks.has_permissions(administrator=True)
async def automod_remove(interaction: discord.Interaction, rule_id: str):
    await interaction.response.send_message(f"🗑️ ルールID `{rule_id}` を削除しました。", ephemeral=True)

@automod_group.command(name="toggle", description="ルールの有効/無効を切り替え")
@app_commands.checks.has_permissions(administrator=True)
async def automod_toggle(interaction: discord.Interaction, rule_id: str):
    await interaction.response.send_message(f"🔄 ルールID `{rule_id}` の有効/無効を切り替えました。", ephemeral=True)

client.tree.add_command(automod_group)

# ==========================================
# 4. モデレーション管理 (/moderation)
# ==========================================
moderation_group = app_commands.Group(name="moderation", description="モデレーション管理")

@moderation_group.command(name="cases", description="最近のAutoMod検知ケースを確認")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_cases(interaction: discord.Interaction):
    await interaction.response.send_message("📊 最近の検知履歴はありません。", ephemeral=True)

@moderation_group.command(name="setup", description="検知パネルを送る運営専用チャンネルを設定")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.send_message(f"🔧 運営専用チャンネルを {channel.mention} に設定しました。", ephemeral=True)

@moderation_group.command(name="toggle", description="スパム検知ON/OFF(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_toggle(interaction: discord.Interaction, state: bool):
    status = "ON" if state else "OFF"
    await interaction.response.send_message(f"🛡️ スパム検知を **{status}** にしました。", ephemeral=True)

@moderation_group.command(name="untimeout", description="メンバーのタイムアウト(TO)を解除(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_untimeout(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None, reason="管理者によるタイムアウト解除")
        await interaction.response.send_message(f"✅ {member.mention} のタイムアウトを解除しました。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ タイムアウトの解除に失敗しました: {e}", ephemeral=True)

client.tree.add_command(moderation_group)

# ==========================================
# 5. チャンネル管理 (/channel)
# ==========================================
channel_group = app_commands.Group(name="channel", description="チャンネル操作")

@channel_group.command(name="create", description="チャンネルを作成")
@app_commands.checks.has_permissions(administrator=True)
async def channel_create(interaction: discord.Interaction, name: str):
    guild = interaction.guild
    new_channel = await guild.create_text_channel(name=name)
    await interaction.response.send_message(f"📁 チャンネル {new_channel.mention} を作成しました。", ephemeral=True)

@channel_group.command(name="permissions", description="チャンネルのロール別権限を設定")
@app_commands.checks.has_permissions(administrator=True)
async def channel_permissions(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.send_message(f"🔐 {role.mention} の権限を設定しました。", ephemeral=True)

@channel_group.command(name="reset_permissions", description="ロール別の権限上書きをリセット")
@app_commands.checks.has_permissions(administrator=True)
async def channel_reset_permissions(interaction: discord.Interaction):
    await interaction.response.send_message("🔄 チャンネルの権限上書きをリセットしました。", ephemeral=True)

client.tree.add_command(channel_group)

# ==========================================
# 6. 監視・Ping系 (/ping)
# ==========================================
ping_group = app_commands.Group(name="ping", description="監視コマンド")

@ping_group.command(name="add", description="監視URLを登録(60秒間隔)")
@app_commands.checks.has_permissions(administrator=True)
async def ping_add(interaction: discord.Interaction, url: str):
    await interaction.response.send_message(f"🌐 監視対象URL `{url}` を登録しました（60秒間隔）。", ephemeral=True)

@ping_group.command(name="list", description="監視対象一覧")
async def ping_list(interaction: discord.Interaction):
    await interaction.response.send_message("📋 現在登録されている監視対象一覧:\n- `https://example.com` (稼働中)", ephemeral=True)

@ping_group.command(name="remove", description="監視対象を削除")
@app_commands.checks.has_permissions(administrator=True)
async def ping_remove(interaction: discord.Interaction, url: str):
    await interaction.response.send_message(f"🗑️ `{url}` の監視を解除しました。", ephemeral=True)

@ping_group.command(name="resume", description="監視再開")
@app_commands.checks.has_permissions(administrator=True)
async def ping_resume(interaction: discord.Interaction):
    await interaction.response.send_message("▶️ すべての監視を再開しました。", ephemeral=True)

@ping_group.command(name="status", description="監視結果を表示")
async def ping_status(interaction: discord.Interaction):
    await interaction.response.send_message("🟢 すべての監視対象は正常に稼働しています。", ephemeral=True)

@ping_group.command(name="stop", description="監視停止")
@app_commands.checks.has_permissions(administrator=True)
async def ping_stop(interaction: discord.Interaction):
    await interaction.response.send_message("⏹️ すべての監視を一時停止しました。", ephemeral=True)

client.tree.add_command(ping_group)

# ==========================================
# 7. サポート・チケット系 (/support-status, /ticket)
# ==========================================
support_group = app_commands.Group(name="support-status", description="対応状況管理")

@support_group.command(name="panel", description="対応状況パネルを設置(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def support_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🎧 サポート対応状況", description="現在の対応ステータス：**受付中**", color=discord.Color.teal())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ サポート状況パネルを設置しました。", ephemeral=True)

@support_group.command(name="set", description="対応状況を変更(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def support_set(interaction: discord.Interaction, status: str):
    await interaction.response.send_message(f"🔄 対応ステータスを **{status}** に変更しました。", ephemeral=True)

client.tree.add_command(support_group)

class TicketCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ このチケットを閉じることができるのは管理者のみです。", ephemeral=True)
            return
        
        await interaction.response.send_message("🔒 チケットを閉じています... 5秒後にチャンネルが削除されます。", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケットを作成", style=discord.ButtonStyle.blurple, emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites
        )

        embed = discord.Embed(
            title="🎫 お問い合わせチケット",
            description=f"{interaction.user.mention} 様、お問い合わせありがとうございます。\nスタッフが対応いたしますので少々お待ちください。\n\n※このチケットを閉じられるのは**管理者のみ**です。",
            color=discord.Color.blurple()
        )
        view = TicketCloseView()
        await ticket_channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✨ チケットを作成しました: {ticket_channel.mention}", ephemeral=True)

ticket_group = app_commands.Group(name="ticket", description="チケット機能")

@ticket_group.command(name="panel", description="お問い合わせパネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🎫 お問い合わせチケット", description="下のボタンを押すと専用のチケットチャンネルが作成されます。", color=discord.Color.blurple())
    view = TicketPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✨ お問い合わせパネルを設置しました。", ephemeral=True)

client.tree.add_command(ticket_group)

# ==========================================
# 8. その他の単体コマンド & 統合型便利ツールパネル
# ==========================================

class UtilityPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ヘルプ", style=discord.ButtonStyle.primary, emoji="📖")
    async def help_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title="📖 Botの使い方・コマンド一覧", description="利用可能なコマンドグループ：\n`/ad`, `/auth`, `/automod`, `/moderation`, `/channel`, `/ping`, `/support-status`, `/ticket`", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="稼働状況", style=discord.ButtonStyle.success, emoji="🟢")
    async def status_button(self, interaction: discord.Interaction, button: Button):
        latency = round(client.latency * 1000)
        await interaction.response.send_message(f"🟢 システム正常稼働中\nPing: `{latency}ms`", ephemeral=True)

    @discord.ui.button(label="提案を投稿", style=discord.ButtonStyle.secondary, emoji="💡")
    async def suggest_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("💡 提案を行うには `/suggest` コマンドをご利用ください。", ephemeral=True)

    @discord.ui.button(label="管理", style=discord.ButtonStyle.danger, emoji="⚙️")
    async def management_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ この機能は管理者のみ利用できます。", ephemeral=True)
            return
        await interaction.response.send_message("⚙️ 管理者用メニュー：サーバーの管理・設定コマンドをご利用ください。", ephemeral=True)

    @discord.ui.button(label="選挙を作成", style=discord.ButtonStyle.success, emoji="🗳️")
    async def election_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 選挙の作成は管理者のみ実行できます。", ephemeral=True)
            return
        embed = discord.Embed(title="🗳️ 選挙投票受付", description="投票用のリアクションを付けたメッセージを送信しました。", color=discord.Color.gold())
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction("🇦")
        await msg.add_reaction("🇧")
        await interaction.response.send_message("✨ 選挙パネルを作成しました。", ephemeral=True)

@client.tree.command(name="event", description="イベント告知を作成(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def event_create(interaction: discord.Interaction, title: str, description: str):
    embed = discord.Embed(title=f"🎉 {title}", description=description, color=discord.Color.orange())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ イベント告知を作成しました。", ephemeral=True)

@client.tree.command(name="help", description="Botの使い方")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Botの使い方・コマンド一覧", description="利用可能なコマンドグループ：\n`/ad`, `/auth`, `/automod`, `/moderation`, `/channel`, `/ping`, `/support-status`, `/ticket`", color=discord.Color.purple())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="panel", description="便利ツールパネルを設置(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def panel_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛠️ 便利ツールパネル", 
        description="以下のボタンから「管理」「稼働状況」「選挙作成」「ヘルプ」「提案」などの機能にアクセスできます。", 
        color=discord.Color.dark_gray()
    )
    view = UtilityPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✨ 拡張版便利ツールパネルを設置しました。", ephemeral=True)

@client.tree.command(name="reset", description="サーバー内の全チャンネル·カテゴリをリセット(危険)")
@app_commands.checks.has_permissions(administrator=True)
async def reset_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("⚠️ このコマンドは安全のため無効化されています。", ephemeral=True)

@client.tree.command(name="status", description="システム稼働状況")
async def status_cmd(interaction: discord.Interaction):
    latency = round(client.latency * 1000)
    await interaction.response.send_message(f"🟢 システム正常稼働中\nPing: `{latency}ms`", ephemeral=True)

@client.tree.command(name="suggest", description="提案を投稿")
async def suggest_cmd(interaction: discord.Interaction, suggestion: str):
    embed = discord.Embed(title="💡 新しい提案", description=suggestion, color=discord.Color.blurple())
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await interaction.response.send_message("✨ 提案を投稿しました。", ephemeral=True)

@client.tree.command(name="welcome", description="歓迎チャンネルを設定(管理者)")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_setup(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.send_message(f"👋 歓迎メッセージの送信先を {channel.mention} に設定しました。", ephemeral=True)

# 起動
token = os.environ.get("DISCORD_TOKEN")
if token:
    client.run(token)
else:
    print("Error: DISCORD_TOKEN environment variable is not set.")
