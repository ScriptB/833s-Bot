# Reaction Roles System Documentation

## Overview

The Guardian Bot's Reaction Roles system is a future-proof, manually configured system that allows server administrators to create role selection panels for members. Unlike automatic systems, this requires explicit admin configuration for security and control.

## Key Features

- **Manual Configuration**: Admins must explicitly add roles - no automatic discovery
- **Group Organization**: Roles can be organized into groups (Games, Interests, Other)
- **Stateful Selection**: Members see their current selections and can modify them
- **Persistent Panels**: Survive bot reboots and redeploys
- **Security Validations**: Prevents assignment of protected/system roles
- **Rate Limit Safe**: Respects Discord's interaction limits

## Commands

### `/reactionroles deploy`
**Permissions**: Administrator or Manage Server
**Purpose**: Deploy or repair the member panel in #reaction-roles channel

**Usage**:
1. Configure roles first using `/reactionroles manage`
2. Run `/reactionroles deploy` to create/update the panel
3. The panel will be created in #reaction-roles channel (auto-created if needed)

### `/reactionroles manage`
**Permissions**: Manage Roles or Administrator
**Purpose**: Open admin management UI for configuring roles

**Management Options**:
- **Add Roles**: Select roles from server to add to reaction roles
- **Remove Roles**: Remove roles from the reaction roles configuration
- **Edit Roles**: Modify group, enabled status, labels, and emojis
- **Reorder**: Change the order of roles in the display
- **Publish**: Update the member panel with current configuration

### `/reactionroles list`
**Permissions**: Manage Roles
**Purpose**: Display all configured roles with their settings

**Output**: Shows groups, role names, enabled status, and order

### `/reactionroles clear_user`
**Permissions**: Manage Roles or Moderator
**Purpose**: Remove all reaction roles from a user

**Note**: Currently clears from the command user. Future versions will support target selection.

### `/reactionroles repair`
**Permissions**: Administrator
**Purpose**: Repair the reaction roles panel

**Use when**: Panel message is missing, broken, or after bot restarts

## Admin Setup Guide

### Step 1: Initial Configuration

1. Run `/reactionroles manage` to open the admin panel
2. Click **"Add Roles"** to configure available roles
3. Select up to 25 roles at a time from the RoleSelect menu
4. Roles will be added with default settings:
   - Group: "games"
   - Enabled: Yes
   - Order: Appended to end

### Step 2: Organize Roles

1. Use **"Edit Roles"** to modify individual roles:
   - Change group (Games/Interests/Other)
   - Toggle enabled/disabled status
   - Set custom labels (optional)
   - Set custom emojis (optional)

2. Use **"Reorder"** to adjust role display order:
   - Select a role and use Up/Down buttons
   - Order affects how roles appear in the member panel

### Step 3: Deploy Panel

1. Click **"Publish"** in the admin panel OR run `/reactionroles deploy`
2. The bot will:
   - Create #reaction-roles channel if it doesn't exist
   - Generate the member panel with current configuration
   - Store panel location for persistence

### Step 4: Test and Verify

1. Test the member panel as a regular user
2. Verify role assignments work correctly
3. Check that protected roles cannot be assigned

## Member Usage

Members interact with the panel in #reaction-roles channel:

1. **Select Roles**: Choose from dropdown menus organized by group
2. **Stateful Updates**: Selecting a role adds it, deselecting removes it
3. **Clear All**: Use the "Clear All Roles" button to remove all reaction roles
4. **Instant Feedback**: Get immediate confirmation of role changes

## Security Features

### Role Validation

The system automatically rejects roles that are:

- `@everyone` role
- Managed/bot roles (integration roles, bot roles)
- Protected system roles (Owner, Admin, Moderator, etc.)
- Roles above the bot's highest role
- Roles with protected names (admin, mod, verified, etc.)

### Permission Checks

- **Admin Commands**: Require Administrator or Manage Roles permission
- **Member Panel**: No special permissions required
- **Channel Security**: Reaction-roles channel restricts member posting

## Persistence and Reliability

### Panel Persistence

- Panel location stored in database (`reaction_roles_panel` key)
- Automatic repair on bot startup
- Message editing instead of spamming new messages
- Rate limiting prevents API abuse

### Data Storage

**ReactionRolesStore Schema**:
```sql
CREATE TABLE reaction_roles_config (
    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    group_key TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    order_index INTEGER NOT NULL,
    label TEXT NULL,
    emoji TEXT NULL,
    PRIMARY KEY (guild_id, role_id)
);
```

**PanelStore Schema**:
```sql
CREATE TABLE panels (
    panel_key TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL
);
```

## Troubleshooting

### Common Issues

**Panel Not Appearing**:
1. Check if #reaction-roles channel exists
2. Verify bot has send permissions in the channel
3. Run `/reactionroles repair` to fix broken panels
4. Check if any roles are configured

**Roles Not Assigning**:
1. Verify bot has Manage Roles permission
2. Check if role is above bot's highest role
3. Ensure role is not a managed/protected role
4. Check if role is enabled in configuration

**Admin Panel Not Working**:
1. Verify user has Manage Roles or Administrator permission
2. Check if interaction responses are enabled
3. Try running the command again

**Panel Not Updating After Changes**:
1. Use the "Publish" button in admin panel
2. Run `/reactionroles deploy` to force update
3. Check for rate limiting (wait 1 second between updates)

### Error Messages

**"No roles configured yet"**:
- Run `/reactionroles manage` and add roles first

**"I don't have permission to manage your roles"**:
- Bot needs Manage Roles permission
- Check role hierarchy (bot role must be above assigned roles)

**"Cannot add managed/bot roles"**:
- These roles are automatically filtered for security
- Choose regular member roles instead

## Advanced Configuration

### Custom Groups

While the system defaults to "games", "interests", and "other", you can use any group names:

1. Edit roles and set custom group names
2. Groups are created automatically as needed
3. Member panel will show all configured groups

### Role Labels and Emojis

Enhance role display with custom labels and emojis:

1. Use **"Edit Roles"** → select a role
2. Set a custom label (overrides role name in display)
3. Set a custom emoji (shows before the role name)

### Large Groups

If a group has more than 25 roles:
- System automatically paginates (Games 1/2, Games 2/2, etc.)
- Each page shows up to 25 roles
- Members can interact with each page independently

## Migration from Old System

If migrating from the previous automatic reaction roles system:

1. The old system has been completely removed
2. All previous configurations are lost
3. New system requires manual setup from scratch
4. Use `/reactionroles manage` to reconfigure roles

## Best Practices

1. **Start Small**: Add a few roles first, test the system, then expand
2. **Use Groups**: Organize roles logically (Games, Interests, Other)
3. **Test Permissions**: Verify role hierarchy before deploying
4. **Regular Maintenance**: Periodically review and update role configurations
5. **Document Changes**: Keep track of role configuration changes for staff

## API Reference

### Store Methods

```python
# Add roles to configuration
await store.add_roles(guild_id, [
    {
        "role_id": 123456789,
        "group_key": "games",
        "enabled": True,
        "label": "Custom Label",
        "emoji": "🎮"
    }
])

# Remove roles
await store.remove_roles(guild_id, [123456789])

# Toggle role enabled status
await store.set_enabled(guild_id, 123456789, True/False)

# Change role group
await store.set_group(guild_id, 123456789, "interests")

# Move role in order
await store.move_role(guild_id, 123456789, "up"/"down")

# List all configured roles
roles = await store.list_roles(guild_id)

# List roles in specific group
games_roles = await store.list_group(guild_id, "games")
```

## Support

For issues or questions about the Reaction Roles system:

1. Check this documentation first
2. Review the troubleshooting section
3. Test with a small number of roles initially
4. Contact the bot administrator for persistent issues
