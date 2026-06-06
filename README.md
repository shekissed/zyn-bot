# 🤖 Zyn Bot

A powerful, multipurpose Discord bot built with **discord.py** and designed to provide comprehensive server management, moderation, automation, and entertainment features.

---

## 📋 Features

Zyn Bot is packed with a wide range of features organized into multiple category modules:

### 🛡️ **Core Categories**
- **Moderation** - Server moderation tools and commands
- **Security** - Advanced security features
- **Automod** - Automatic moderation systems
- **Utility** - General-purpose utility commands
- **Social** - Social interaction features
- **Guild** - Server management tools
- **Owner** - Owner-only commands
- **Events** - Event handling and management

### 🎯 **Key Features**
- **Sharded Bot Architecture** - Supports 12 shards for optimal performance across large server networks
- **Dynamic Prefix System** - Customize per-guild command prefix
- **Premium Tier System** - Support for premium guild features with expiration tracking
- **Profile Cards** - Beautiful customizable profile cards with user avatars and status indicators
- **Music Features** - Wavelink integration for music playback
- **AI Integration** - OpenAI powered features
- **Chess Support** - Built-in chess game functionality
- **Text-to-Speech** - Multiple TTS options (pyttsx3 and gtts)
- **Game Search** - DuckDuckGo integration for web search
- **Database Support** - SQLite for core operations, MongoDB for scalability
- **Jishaku Integration** - Developer debugging tools

---

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager
- Discord Bot Token
- (Optional) MongoDB for advanced features

### Setup Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/shekissed/zyn-bot.git
   cd zyn-bot
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create Environment File**
   Create a `.env` file in the root directory:
   ```env
   TOKEN=your_discord_bot_token_here
   ```

4. **Run the Bot**
   ```bash
   python main.py
   ```

---

## 📦 Dependencies

Key dependencies include:
- **discord.py** - Discord API wrapper
- **aiosqlite** - Async SQLite support
- **wavelink** - Music streaming (v3.0.0+)
- **Pillow** - Image processing for profile cards
- **jishaku** - Developer debugging extension
- **openai** - AI-powered features
- **duckduckgo-search** - Web search integration
- **FastAPI & Uvicorn** - Optional API server
- **pymongo & motor** - MongoDB support
- Plus 20+ additional specialized libraries

---

## 🎨 Project Structure

```
zyn-bot/
├── main.py                    # Main bot entry point
├── card_generator.py          # Profile card generation engine
├── emojis.py                  # Custom emoji definitions
├── requirements.txt           # Python dependencies
├── .env                       # Environment configuration
├── .gitignore                 # Git ignore rules
├── cogs/                      # Command modules
│   ├── moderation/            # Moderation commands
│   ├── security/              # Security features
│   ├── automod/               # Automod systems
│   ├── utility/               # Utility commands
│   ├── social/                # Social features
│   ├── guild/                 # Guild management
│   ├── owner/                 # Owner commands
│   └── events/                # Event handlers
├── db/                        # Database files
│   ├── core.db                # Core database
│   ├── premium.db             # Premium tier data
│   └── tracker.db             # User tracking data
└── assets/                    # Static assets

```

---

## 💻 Commands

### Prefix Management
- `.setprefix <prefix>` - Set custom server prefix (Admin only)
- `.resetprefix` - Reset prefix to default (Admin only)

Default prefix: `.`

---

## 🔧 Configuration

### Bot Settings (in `main.py`)
- **Owner IDs** - Users with full bot control
- **Developer IDs** - Developer access levels
- **Shard Count** - Currently set to 12 shards
- **Premium Links** - Support, invite, and voting links

### Database Configuration
The bot uses three separate databases:
1. **core.db** - Prefixes, developer reactions, no-prefix users
2. **premium.db** - Premium guild data with expiration
3. **tracker.db** - User message tracking and daily counts

---

## 🎭 Profile Card Generator

The `card_generator.py` module creates beautiful Discord profile cards with:
- Full-bleed blurred background
- Circular avatar with status indicator
- Display name and username
- Optional clan tag pill
- Join date information
- Custom styling matching modern Discord aesthetics

**Status Indicators:**
- 🟢 Online (Green)
- 🌙 Idle (Yellow)
- 🔴 Do Not Disturb (Red)
- ⚫ Offline (Gray)

---

## 🌐 Bot Status Rotation

The bot cycles through dynamic statuses displaying:
- Server protection status
- Guild count
- Active member count
- Help command reference
- Musical information

---

## 📚 Development

### Loading Cogs
The bot automatically loads all Python files from configured cog directories. Each cog directory must have an `__init__.py` file to be recognized as a Python package.

### Adding New Commands
1. Create a new file in the appropriate `cogs/` subdirectory
2. Inherit from `commands.Cog`
3. Add your command methods
4. The bot will automatically load it on startup

### Database Queries
Use `aiosqlite` for async database operations:
```python
async with aiosqlite.connect(CORE_DB) as db:
    async with db.execute("SELECT * FROM prefixes WHERE guild_id = ?", (guild_id,)) as cursor:
        row = await cursor.fetchone()
```

---

## 🔐 Premium System

The bot includes a tiered premium system:
- **Premium Guilds** - Unlock exclusive features (ChangeAvatar, ChangeBanner, ChangeBio)
- **Trial System** - Track one-time trial usage per guild
- **Expiration Tracking** - Automatic expiration on specific timestamps

Premium locked commands require an active subscription:
- Commands are blocked if guild lacks premium tier
- Expired premium shows renewal prompt
- Support link provided for subscription info

---

## 🎯 Slash Commands

In addition to prefix commands, the bot supports Discord's slash commands (Application Commands):
- Slash commands are automatically synced on bot startup
- New slash commands register globally on the bot

---

## 🐛 Debugging & Development

### Jishaku Extension
For development debugging, the bot loads **Jishaku** (owner-only):
- Code evaluation
- SQL queries
- Task management
- Performance profiling

### Debug Mode
Enable debug output in `debug_jsk.py` for advanced diagnostics.

---

## 📊 Statistics & Monitoring

The bot provides real-time statistics:
- **Uptime** - Continuous tracking since startup
- **Guild Count** - Number of servers the bot serves
- **Member Count** - Total members across all servers
- **Shard Status** - Individual shard connection status
- **CPU/RAM/Storage** - System resource monitoring
- **Database Size** - Core database metrics

---

## 🤝 Support & Community

**Discord Community:** [Join Developers Concept](https://discord.gg/ggTv7Zx4eg)

For issues, feature requests, or community support, visit our Discord server.

**Bot Developer Profile:** [User ID: 1043752570243526757](https://discord.com/users/1043752570243526757)

---

## 📝 License

This project is maintained by **Developers Concept** community.

---

## ✨ Credits

**Developed by:** shekissed  
**Community:** [Developers Concept Discord Server](https://discord.gg/ggTv7Zx4eg)  
**Developer:** [Discord Profile](https://discord.com/users/1043752570243526757)

---

## 🚀 Getting Started

1. Invite the bot to your server
2. Use `.help` to see all available commands
3. Customize your prefix with `.setprefix <prefix>`
4. Explore premium features in the support server
5. Join the community for updates and support

---

**Thanks for choosing Zyn Bot! 🎉**
