# Linux Installation Instructions

This guide explains how to properly install Intune Manager on Linux with desktop integration and application icons.

## Quick Install

```bash
# 1. Copy the binary to your PATH
sudo cp intune_manager.bin /usr/local/bin/intune_manager
sudo chmod +x /usr/local/bin/intune_manager

# 2. Install icons (from assets/icons/ directory)
for size in 16 32 48 64 128 256 512; do
  mkdir -p ~/.local/share/icons/hicolor/${size}x${size}/apps
  cp assets/icons/icon-${size}.png ~/.local/share/icons/hicolor/${size}x${size}/apps/intune-manager.png
done

# 3. Install desktop file
mkdir -p ~/.local/share/applications
cp assets/intune-manager.desktop ~/.local/share/applications/

# 4. Update desktop database
update-desktop-database ~/.local/share/applications/

# 5. Update icon cache
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor/
```

## Manual Installation

### Step 1: Install Binary

Copy the compiled binary to a directory in your PATH:

**User installation:**
```bash
mkdir -p ~/.local/bin
cp intune_manager.bin ~/.local/bin/intune_manager
chmod +x ~/.local/bin/intune_manager
```

**System-wide installation (requires sudo):**
```bash
sudo cp intune_manager.bin /usr/local/bin/intune_manager
sudo chmod +x /usr/local/bin/intune_manager
```

### Step 2: Install Icons

Install application icons at all standard sizes for proper desktop integration:

```bash
# Create icon directories
for size in 16 32 48 64 128 256 512; do
  mkdir -p ~/.local/share/icons/hicolor/${size}x${size}/apps
done

# Copy icons (adjust path to where you extracted assets/icons/)
cp assets/icons/icon-16.png ~/.local/share/icons/hicolor/16x16/apps/intune-manager.png
cp assets/icons/icon-32.png ~/.local/share/icons/hicolor/32x32/apps/intune-manager.png
cp assets/icons/icon-48.png ~/.local/share/icons/hicolor/48x48/apps/intune-manager.png
cp assets/icons/icon-64.png ~/.local/share/icons/hicolor/64x64/apps/intune-manager.png
cp assets/icons/icon-128.png ~/.local/share/icons/hicolor/128x128/apps/intune-manager.png
cp assets/icons/icon-256.png ~/.local/share/icons/hicolor/256x256/apps/intune-manager.png
cp assets/icons/icon-512.png ~/.local/share/icons/hicolor/512x512/apps/intune-manager.png
```

### Step 3: Install Desktop File

1. Copy the desktop file:
   ```bash
   mkdir -p ~/.local/share/applications
   cp assets/intune-manager.desktop ~/.local/share/applications/
   ```

2. Edit the desktop file if you installed the binary to a different location:
   ```bash
   nano ~/.local/share/applications/intune-manager.desktop
   # Update the Exec= line to match your installation path
   ```

3. Update the desktop database:
   ```bash
   update-desktop-database ~/.local/share/applications/
   ```

### Step 4: Update Icon Cache

Update the icon cache so desktop environments recognize the new icons:

```bash
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor/
```

If you don't have `gtk-update-icon-cache`, you may need to log out and back in for icons to appear.

## Verification

After installation, you should be able to:

1. **Launch from terminal:**
   ```bash
   intune_manager
   ```

2. **Launch from application menu:**
   - Search for "Intune Manager" in your application launcher
   - The app should appear with the orange device management icon

3. **See icon in taskbar:**
   - When running, the icon should appear in your system panel/taskbar

## Troubleshooting

### Application doesn't appear in menu

- Run `update-desktop-database ~/.local/share/applications/`
- Log out and log back in
- Check that the Exec path in the desktop file is correct

### Icon doesn't show

- Run `gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor/`
- Check that icon files are installed in the correct directories
- Verify file permissions (should be readable: `chmod 644 ~/.local/share/icons/hicolor/*/apps/intune-manager.png`)

### Binary not found

- Ensure ~/.local/bin is in your PATH:
  ```bash
  echo $PATH | grep -q "$HOME/.local/bin" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  source ~/.bashrc
  ```

## Uninstallation

```bash
# Remove binary
rm ~/.local/bin/intune_manager
# or
sudo rm /usr/local/bin/intune_manager

# Remove desktop file
rm ~/.local/share/applications/intune-manager.desktop

# Remove icons
rm ~/.local/share/icons/hicolor/*/apps/intune-manager.png

# Update caches
update-desktop-database ~/.local/share/applications/
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor/
```

## Distribution-Specific Notes

### Ubuntu/Debian
All commands should work as-is. Package `desktop-file-utils` provides `update-desktop-database`.

### Fedora/RHEL
All commands should work as-is. Package `desktop-file-utils` provides `update-desktop-database`.

### Arch Linux
All commands should work as-is. Package `desktop-file-utils` provides `update-desktop-database`.

### Other Distributions
Most modern Linux distributions follow the freedesktop.org standards, so these instructions should work universally. If you encounter issues, consult your distribution's documentation for installing .desktop files and icons.
