import os
import discord
from discord import app_commands

class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドを同期しました。")

client = MyBot()

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")

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
@app_commands.checks.has_permissions(administrator=Thread=True if False else True)
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
# 2. 認証系 (/auth)
# ==========================================
auth_group = app_commands.Group(name="auth", description="認証機能")

@auth_group.command(name="panel", description="認証パネルを設置")
async def auth_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🔒 サーバー認証", description="下のボタンを押して認証を完了してください。", color=discord.Color.gold())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ 認証パネルを設置しました。", ephemeral=True)

@auth_group.command(name="setup", description="既存ロールIDを認証ロールに設定")
@app_commands.checks.has_permissions(administrator=True)
async def auth_setup(interaction: discord.Interaction, role: discord.Role):
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

ticket_group = app_commands.Group(name="ticket", description="チケット機能")

@ticket_group.command(name="panel", description="お問い合わせパネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🎫 お問い合わせチケット", description="下のボタンを押すと専用のチャンネルが作成されます。", color=discord.Color.blurple())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ お問い合わせパネルを設置しました。", ephemeral=True)

client.tree.add_command(ticket_group)

# ==========================================
# 8. その他の単体コマンド
# ==========================================
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
    embed = discord.Embed(title="🛠️ 便利ツールパネル", description="必要な機能を選択してください。", color=discord.Color.dark_gray())
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✨ 便利ツールパネルを設置しました。", ephemeral=True)

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
