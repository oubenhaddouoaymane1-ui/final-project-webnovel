# CineOS Telegram Bot Guide

The Telegram bot is the primary user interface for CineOS. Users send novel files through Telegram, monitor progress, and receive final videos — all within the chat.

## Bot Setup

### Creating a Bot with BotFather

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Enter a display name (e.g., "CineOS Bot")
4. Enter a username ending in `bot` (e.g., `mycineos_bot`)
5. Copy the token BotFather returns

### Configuring the Bot

Set the token in your `.env` file:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
```

Restart the bot:

```bash
docker compose restart telegram_bot
```

### Bot Configuration File

Edit `config/telegram.yaml` to customize behavior:

```yaml
bot:
  name: "CineOS Bot"
  description: "Novel to Cinematic Video Production Bot"

limits:
  max_file_size_mb: 50
  min_words: 50
  max_words: 500000
  allowed_extensions:
    - ".txt"
    - ".md"
  max_active_projects_per_user: 1
  cooldown_seconds: 60
```

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and instructions |
| `/status` | Check current project progress |
| `/cancel` | Cancel current project |
| `/help` | Show help message |

## How It Works

### Sending a Novel

1. Open a chat with your CineOS bot
2. Send `/start` to see the welcome message
3. Send a `.txt` file containing your novel
4. The bot validates the file and creates a project
5. Processing begins automatically

### File Requirements

| Requirement | Value |
|-------------|-------|
| Format | `.txt` or `.md` |
| Encoding | UTF-8 |
| Min words | 50 |
| Max words | 500,000 |
| Max file size | 50 MB |

### Progress Notifications

The bot sends notifications at key milestones:

| Milestone | When |
|-----------|------|
| Project created | Immediately after file upload |
| 25% complete | Parsing and analysis finished |
| 50% complete | Image generation complete |
| 75% complete | Audio and animation complete |
| 100% complete | Video delivered |

Configure notification settings in `config/telegram.yaml`:

```yaml
notifications:
  on_project_created: true
  on_state_change: false
  on_progress_milestone: true
  milestone_intervals: [25, 50, 75, 100]
  on_delivery: true
  on_failure: true
```

### Checking Status

Send `/status` to get a progress update:

```
📊 Project: The Great Adventure
State: generating
Progress: 50%
Scenes: 24/48
```

### Cancelling a Project

Send `/cancel` to stop the current project. The project state changes to `cancelled` and all pending jobs are removed.

## Receiving Output

When processing completes, the bot sends the final video. For large files, the bot may:

1. Send a compressed version first
2. Offer a download link for the full-quality version
3. Provide a summary of the production

## Troubleshooting

### Bot Won't Start

1. Verify the token is correct:

```bash
# Test the token
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```

2. Check bot logs:

```bash
docker compose logs -f telegram_bot
```

3. Verify the n8n webhook is accessible:

```bash
curl http://localhost:5678/healthz
```

### Bot Doesn't Respond to Messages

1. Check the bot is running:

```bash
docker compose ps telegram_bot
```

2. Verify no other bot instance is using the same token (Telegram only allows one connection per token).

3. Check for rate limiting:

```bash
docker compose logs telegram_bot | grep -i "rate\|429\|too many"
```

### File Upload Fails

1. Check file size is under the limit (default 50MB)
2. Verify file encoding is UTF-8
3. Check the bot has write permissions to the temp directory

### Bot Responds But Project Never Starts

1. Check n8n is running and healthy:

```bash
curl http://localhost:5678/healthz
```

2. Verify the webhook URL is correct in the bot configuration

3. Check n8n execution history for errors:

```bash
# Open n8n UI at http://localhost:5678
# Go to Executions tab to see recent runs
```

### Video Delivery Fails

1. Check the render worker is healthy:

```bash
curl http://localhost:8300/health
```

2. Verify output directory has free space:

```bash
df -h output/
```

3. Check Telegram file size limits (bots can send files up to 50MB)

## Customization

### Changing Welcome Message

Edit `config/telegram.yaml`:

```yaml
messages:
  welcome: |
    🎬 Welcome to CineOS!
    Send me a novel (.txt file) and I'll create a cinematic video.
```

### Adjusting Limits

```yaml
limits:
  max_file_size_mb: 50        # Max upload size
  min_words: 50               # Minimum word count
  max_words: 500000           # Maximum word count
  max_active_projects_per_user: 1
  cooldown_seconds: 60        # Between uploads
```

### Multi-Language Support

The bot supports multiple languages. Set the default in `.env`:

```env
DEFAULT_LANGUAGE=en
```

When a user sends a novel, the bot detects the language and uses appropriate TTS voices.

### Adding Custom Commands

To add custom commands, edit the bot handler in `src/telegram/bot.py`. Each command is a method decorated with the command handler:

```python
@self.application.command_handler(CommandHandler("mycommand", self.my_command))
async def my_command(self, update, context):
    await update.message.reply_text("Custom response!")
```

## Architecture

The Telegram bot runs as a Docker container and communicates with:

1. **PostgreSQL** — Stores user data and project state
2. **n8n** — Sends webhook triggers for workflow execution
3. **Redis** — Session caching and rate limiting

```
Telegram API ←→ Bot Container ←→ PostgreSQL
                    ↓
                    n8n Webhook
                    ↓
              n8n Workflows
```

The bot itself does NOT process novels — it only handles user interaction and delegates all processing to n8n workflows.
