#!/usr/bin/env python3
"""
CompDeploy v1.0 - Fusion Studio + Nuke Support
Creates both Fusion Studio .comp files and Foundry Nuke .nk files from selected media pool clips
with automatic version incrementing, EXR export settings, customizable output paths,
VFX Notes extraction from Comments and Description fields as StickyNotes,
smart version control (independent versioning for each format),
and configurable color management for Nuke scripts.
"""

import json
import os
import platform
import re
import sys
import datetime
from pathlib import Path

# Cross-platform DaVinci Resolve environment setup
def setup_resolve_paths():
    system = platform.system()

    if system == "Darwin":  # macOS
        api_path = '/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so'
        lib_path = '/Applications/DaVinci Resolve/Developer/Scripting/Modules/'

    elif system == "Windows":
        # Try common Windows installation paths
        possible_bases = [
            r'C:\Program Files\Blackmagic Design\DaVinci Resolve',
            r'C:\Program Files (x86)\Blackmagic Design\DaVinci Resolve',
            r'C:\Program Files\Blackmagic Design\DaVinci Resolve Studio'
        ]

        api_path = None
        lib_path = None

        for base in possible_bases:
            test_api = os.path.join(base, 'fusionscript.dll')
            test_lib = os.path.join(base, 'Developer', 'Scripting', 'Modules')

            if os.path.exists(test_api) and os.path.exists(test_lib):
                api_path = test_api
                lib_path = test_lib
                break

        # Fallback to default path if not found
        if not api_path:
            api_path = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll'
            lib_path = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules'

    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

    return api_path, lib_path

# Force set environment variables if not found
try:
    api_path, lib_path = setup_resolve_paths()

    if not os.environ.get('RESOLVE_SCRIPT_API'):
        os.environ['RESOLVE_SCRIPT_API'] = api_path

    if not os.environ.get('RESOLVE_SCRIPT_LIB'):
        os.environ['RESOLVE_SCRIPT_LIB'] = lib_path

    # Add to Python path
    if lib_path not in sys.path:
        sys.path.append(lib_path)

    print(f"✅ {platform.system()}: DaVinci Resolve environment configured")

except Exception as e:
    print(f"⚠️  Environment setup warning: {e}")
    print("Continuing with existing environment variables...")

# GUI Framework
try:
    from PySide6.QtWidgets import *
    from PySide6.QtCore import *
    from PySide6.QtGui import *
except ImportError:
    try:
        from PySide2.QtWidgets import *
        from PySide2.QtCore import *
        from PySide2.QtGui import *
    except ImportError:
        print("PySide not available")
        sys.exit(1)


def write_file_atomically(filepath, content, encoding='utf-8'):
    """
    Write file atomically - either succeeds completely or fails safely.
    
    Args:
        filepath: Path to the target file
        content: Content to write
        encoding: File encoding (default: utf-8)
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        filepath = Path(filepath)
        temp_path = filepath.with_suffix(filepath.suffix + '.tmp')
        
        # Ensure parent directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temporary file first
        with open(temp_path, 'w', encoding=encoding) as f:
            f.write(content)
            f.flush()  # Ensure data is written to OS buffer
            # Force write to disk on Unix systems
            if hasattr(os, 'fsync'):
                os.fsync(f.fileno())
        
        # Atomic rename/move (this is the atomic operation)
        temp_path.replace(filepath)
        
        return True, f"Successfully wrote {filepath.name}"
        
    except Exception as e:
        # Clean up temporary file if it exists
        if 'temp_path' in locals() and temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass  # Ignore cleanup errors
        
        return False, f"Failed to write {filepath.name if 'filepath' in locals() else 'file'}: {e}"


class ResolveTheme:
    """DaVinci Resolve inspired dark theme matching the exact GUI screenshot"""

    @staticmethod
    def get_main_stylesheet():
        return """/* Dark Modern Interface */
                QMainWindow {
                    background: #525252;
                    color: #cccccc;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif;
                    font-size: 13px;
                }

                QWidget {
                    background: #282828;
                    color: #cccccc;
                }

                /* Group Boxes - Exact Panel Style */
                QGroupBox {
                    font-weight: 600;
                    font-size: 13px;
                    color: #ffffff;
                    border: 1px solid #3a3a3a;
                    border-radius: 6px;
                    margin-top: 10px;
                    padding-top: 12px;
                    background: #2a2a2a;
                }

                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 8px;
                    color: #cccccc;
                    background-color: transparent;
                    font-weight: 600;
                    font-size: 13px;
                }

                /* Labels */
                QLabel {
                    color: #cccccc;
                    font-size: 13px;
                    background-color: transparent;
                }

                .title-label {
                    font-size: 22px;
                    font-weight: 600;
                    color: #4376A1;
                    margin: 8px 0;
                }

                .section-title {
                    font-size: 13px;
                    font-weight: 600;
                    color: #cccccc;
                    margin-bottom: 6px;
                }

                .path-label {
                    font-family: 'SF Mono', 'Monaco', 'Menlo', 'Consolas', monospace;
                    color: #aaaaaa;
                    background: #1a1a1a;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-size: 11px;
                }

                .status-success {
                    color: #0C0C0C;
                    font-weight: 500;
                    background: #4376A1;
                    border: 1px solid #4376A1;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                }

                .status-error {
                    color: #ffffff;
                    font-weight: 500;
                    background: #f44336;
                    border: 1px solid #f44336;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                }

                .status-info {
                    color: #0C0C0C;
                    font-weight: 500;
                    background: #2196F3;
                    border: 1px solid #2196F3;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                }

                /* Buttons - Exact Style */
                QPushButton {
                    background: #404040;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    color: #cccccc;
                    font-weight: 500;
                    font-size: 13px;
                    padding: 8px 16px;
                    min-height: 16px;
                    min-width: 80px;
                }

                QPushButton:hover {
                    background: #4a4a4a;
                    border-color: #666666;
                    color: #ffffff;
                }

                QPushButton:pressed {
                    background: #353535;
                    border-color: #666666;
                }

                QPushButton:disabled {
                    background: #2a2a2a;
                    color: #666666;
                    border-color: #333333;
                }

                /* Primary Button - Green Success Style */
                .primary-button {
                    background: #4376A1;
                    border: 1px solid #4376A1;
                    color: #0C0C0C;
                    font-weight: 600;
                }

                .primary-button:hover {
                    background: #5cbf60;
                    border-color: #5cbf60;
                }

                .primary-button:pressed {
                    background: #43a047;
                    border-color: #43a047;
                }

                /* Success Button - Same as Primary */
                .success-button {
                    background: #4376A1;
                    border: 1px solid #4376A1;
                    color: #0C0C0C;
                    font-weight: 600;
                }

                .success-button:hover {
                    background: #5cbf60;
                    border-color: #5cbf60;
                }

                .success-button:pressed {
                    background: #43a047;
                    border-color: #43a047;
                }

                /* Small Button */
                .small-button {
                    padding: 6px 12px;
                    min-height: 12px;
                    min-width: 60px;
                    font-size: 12px;
                }

                /* Input Fields - Dark Style */
                QLineEdit {
                    background: #1a1a1a;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    color: #cccccc;
                    font-size: 13px;
                    padding: 8px 12px;
                    selection-background-color: #4376A1;
                    selection-color: #ffffff;
                }

                QLineEdit:focus {
                    border-color: #4376A1;
                    background: #1f1f1f;
                }

                QLineEdit:hover {
                    border-color: #4a4a4a;
                }

                /* Combo Boxes - Dark Style */
                QComboBox {
                    background: #1a1a1a;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    color: #cccccc;
                    font-size: 13px;
                    padding: 8px 12px;
                    min-width: 120px;
                }

                QComboBox:hover {
                    background: #1f1f1f;
                    border-color: #4a4a4a;
                }

                QComboBox:focus {
                    border-color: #4376A1;
                }

                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                }

                QComboBox::down-arrow {
                    image: none;
                    border-style: solid;
                    border-width: 4px 3px 0 3px;
                    border-color: #cccccc transparent transparent transparent;
                }

                QComboBox QAbstractItemView {
                    background: #2a2a2a;
                    color: #cccccc;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    selection-background-color: #4376A1;
                    selection-color: #ffffff;
                    padding: 2px;
                }

                QComboBox QAbstractItemView::item {
                    padding: 6px 12px;
                    border: none;
                    min-height: 20px;
                }

                QComboBox QAbstractItemView::item:hover {
                    background-color: #404040;
                }

                QComboBox QAbstractItemView::item:selected {
                    background-color: #4376A1;
                    color: #ffffff;
                }

                /* Spin Boxes */
                QSpinBox {
                    background: #1a1a1a;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    color: #cccccc;
                    font-size: 13px;
                    padding: 8px 12px;
                }

                QSpinBox:focus {
                    border-color: #F9423F;
                }

                QSpinBox:hover {
                    border-color: #4a4a4a;
                }

                QSpinBox::up-button, QSpinBox::down-button {
                    width: 0px;
                    height: 0px;
                    border: none;
                    background: none;
                }

                /* Check Boxes - Exact Style */
                QCheckBox {
                    color: #cccccc;
                    font-size: 13px;
                    spacing: 8px;
                }

                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 2px solid #3a3a3a;
                    border-radius: 3px;
                    background: #1a1a1a;
                }

                QCheckBox::indicator:hover {
                    background: #1f1f1f;
                    border-color: #4a4a4a;
                }

                QCheckBox::indicator:checked {
                    background: #F9423F;
                    border-color: #F9423F;
                }

                QCheckBox::indicator:checked:hover {
                    background: #fa5a57;
                    border-color: #fa5a57;
                }

                /* Text Edit - Console Style */
                QTextEdit {
                    background: #1a1a1a;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    color: #cccccc;
                    font-family: 'SF Mono', 'Monaco', 'Menlo', 'Consolas', monospace;
                    font-size: 12px;
                    padding: 12px;
                    selection-background-color: #4376A1;
                    selection-color: #ffffff;
                }

                QTextEdit:focus {
                    border-color: #4376A1;
                }

                /* Scroll Bars - Minimal Style */
                QScrollBar:vertical {
                    background: #2a2a2a;
                    width: 10px;
                    border-radius: 5px;
                    margin: 0;
                }

                QScrollBar::handle:vertical {
                    background: #555555;
                    border-radius: 5px;
                    min-height: 20px;
                    margin: 1px;
                }

                QScrollBar::handle:vertical:hover {
                    background: #666666;
                }

                QScrollBar::handle:vertical:pressed {
                    background: #777777;
                }

                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    border: none;
                    background: none;
                    height: 0px;
                }

                QScrollBar:horizontal {
                    background: #2a2a2a;
                    height: 10px;
                    border-radius: 5px;
                    margin: 0;
                }

                QScrollBar::handle:horizontal {
                    background: #555555;
                    border-radius: 5px;
                    min-width: 20px;
                    margin: 1px;
                }

                QScrollBar::handle:horizontal:hover {
                    background: #666666;
                }

                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    border: none;
                    background: none;
                    width: 0px;
                }

                /* Table Widget - Dark Style */
                QTableWidget {
                    background: #1a1a1a;
                    alternate-background-color: #1f1f1f;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    color: #cccccc;
                    gridline-color: #333333;
                    font-size: 12px;
                }

                QTableWidget::item {
                    padding: 6px;
                    border: none;
                }

                QTableWidget::item:selected {
                    background-color: #4376A1;
                    color: #ffffff;
                }

                QTableWidget::item:hover {
                    background-color: #333333;
                }

                QHeaderView::section {
                    background: #2a2a2a;
                    color: #cccccc;
                    border: 1px solid #3a3a3a;
                    padding: 6px;
                    font-weight: 600;
                    font-size: 12px;
                }

                QHeaderView::section:hover {
                    background: #333333;
                }

                /* Dialog Styling */
                QDialog {
                    background: #1e1e1e;
                    color: #cccccc;
                }

                /* Form Layout */
                QFormLayout QLabel {
                    font-weight: 500;
                    color: #cccccc;
                    min-width: 80px;
                    font-size: 13px;
                }

                /* Tooltips */
                QToolTip {
                    background: #2a2a2a;
                    color: #ffffff;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 6px 8px;
                    font-size: 12px;
                }

                /* Menu Bar and Menus */
                QMenuBar {
                    background: #2a2a2a;
                    color: #cccccc;
                    border: none;
                }

                QMenuBar::item {
                    background: transparent;
                    padding: 6px 12px;
                }

                QMenuBar::item:selected {
                    background: #4376A1;
                    color: #ffffff;
                }

                QMenu {
                    background: #2a2a2a;
                    color: #cccccc;
                    border: 1px solid #3a3a3a;
                }

                QMenu::item {
                    padding: 6px 20px;
                    border: none;
                }

                QMenu::item:selected {
                    background: #4376A1;
                    color: #ffffff;
                }

                /* Splitter */
                QSplitter::handle {
                    background: #3a3a3a;
                }

                QSplitter::handle:vertical {
                    height: 2px;
                }

                QSplitter::handle:horizontal {
                    width: 2px;
                }

                /* Progress Bar */
                QProgressBar {
                    background: #1a1a1a;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                    text-align: center;
                    color: #cccccc;
                    font-size: 12px;
                }

                QProgressBar::chunk {
                    background: #4376A1;
                    border-radius: 3px;
                }

                /* Status Bar */
                QStatusBar {
                    background: #2a2a2a;
                    color: #cccccc;
                    border-top: 1px solid #3a3a3a;
                }
        """


class SettingsManager:
    """Manages user settings and preferences with simplified render path support"""

    def __init__(self):
        self.settings_dir = Path.home() / "Documents" / "CompDeploy"
        self.settings_file = self.settings_dir / "CompDeploy_settings.json"
        self.default_settings = {
                # Output paths - separate for each format (SCRIPT locations)
                "fusion_output_path": "<shotdir>comp/work/fusion/<shotname>_comp_v<version>.comp",
                "nuke_output_path": "<shotdir>comp/work/nuke/<shotname>_comp_v<version>.nk",
                
                # NEW: Separate paths for specialized comps
                "fusion_depth_output_path": "<shotdir>comp/work/fusion/depth/<shotname>_depth_v<version>.comp",
                "fusion_mmask_output_path": "<shotdir>comp/work/fusion/mmask/<shotname>_mmask_v<version>.comp",

                # Render output paths (RENDER locations)
                "fusion_render_path": "<shotdir>comp/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_0000.exr",
                "nuke_render_path": "<shotdir>comp/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_%04d.exr",

                # Render output paths (RENDER locations) - simplified with direct folder typing
                "fusion_render_path": "<shotdir>comp/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_0000.exr",
                "nuke_render_path": "<shotdir>comp/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_%04d.exr",

                # Format generation options
                "generate_fusion": True,
                "generate_nuke": True,

                # NEW: Specialized Fusion comp types
                "generate_fusion_depth": False,
                "generate_fusion_mmask": False,

                 # NEW: Render paths for specialized comps
                "fusion_depth_render_path": "<shotdir>comp/elements/depth/<shotname>_depth_v<version>/<shotname>_depth_v<version>_0000.exr",
                "fusion_mmask_render_path": "<shotdir>comp/elements/mmask/<shotname>_mmask1_v<version>/<shotname>_mmask1_v<version>_0000.exr",

                # Color management for Nuke
                "nuke_color_management": "nuke_default",

                # Custom OCIO settings
                "custom_ocio_config": "",
                "custom_ocio_plate_colorspace": "ACEScct",  # Common plate colorspace
                "custom_ocio_working_space": "scene_linear",
                "custom_ocio_display": "ACES",
                "custom_ocio_view": "Rec.709",
                "custom_ocio_viewer_process": "Rec.709 (ACES)",

                # EXR settings (shared between formats)
                "exr_compression": 9,  # DWAB
                "exr_bit_depth": 1,    # 16-bit Float
                "exr_quality": 45,     # For DWAA/DWAB only

                # VFX Notes settings
                "include_vfx_notes": True,
                "notes_position": "top",

                # Version control
                "overwrite_existing": False,

                # Scene report generation
                "generate_scene_report": True,

                # Creates additional folder structure
                "create_folder_structure": False,

                # Single sequence mode (FIXED)
                "single_sequence_mode": False,
                "metadata_injection": True,
                "metadata_field_name": "shoot_scene_take",
        }
        self.settings = self.load_settings()
        self.folder_manager = FolderStructureManager(self)

    def load_settings(self):
        """Load settings from JSON file"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    merged_settings = self.default_settings.copy()
                    merged_settings.update(settings)
                    return merged_settings
        except Exception as e:
            print(f"Error loading settings: {e}")

        return self.default_settings.copy()

    def save_settings(self):
        """Save settings to JSON file using atomic writing"""
        try:
            # Ensure directory exists
            self.settings_dir.mkdir(parents=True, exist_ok=True)

            settings_json = json.dumps(self.settings, indent=2)
            success, message = write_file_atomically(self.settings_file, settings_json)
            
            if not success:
                print(f"Error saving settings: {message}")
                return False
            
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get_setting(self, key):
        """Get a setting value"""
        return self.settings.get(key, self.default_settings.get(key))

    def set_setting(self, key, value):
        """Set a setting value"""
        self.settings[key] = value

    def get_available_tokens(self):
        """Get list of available path tokens with descriptions - simplified for both script and render paths"""
        return {
            # Standard tokens used for both script and render paths
            "<shotdir>": "Relative path to the shot directory (e.g., /bz_av_sh0020/)",
            "<shotname>": "Name of the shot (e.g., bz_av_sh0020)",
            "<version>": "New/incremented version number (e.g., 001)",
            "<current_version>": "Current source version number",
            "<v###>": "New version with v prefix (e.g., v001)",
            "<cv###>": "Current version with v prefix (e.g., v000)",
            "<filename>": "Base filename without extension",
            "<ext>": "File extension (.comp or .nk)",
            
            # Frame numbering for render paths only
            "0000": "Frame numbering for Fusion (e.g., image_0000.exr, image_0001.exr)",
            "%04d": "Frame numbering for Nuke (e.g., %04d becomes 0001, 0002, 1001)"
        }

    def replace_tokens(self, path_template, token_values):
        """Replace tokens in path template with actual values - works for both script and render paths"""
        result = path_template

        for token, value in token_values.items():
            if token in result:
                result = result.replace(token, str(value))

        return result

    def get_render_path_preview(self, format_type='fusion'):
        """Get preview of render path with example values - simplified approach"""
        
        if format_type == 'fusion':
            template = self.get_setting("fusion_render_path")
        else:
            template = self.get_setting("nuke_render_path")
            
        # Use same token values as script paths
        example_tokens = {
            "<shotdir>": "/bz_av_sh0010",
            "<shotname>": "bz_av_sh0010",
            "<version>": "001",
            "<current_version>": "000",
            "<v###>": "v001",
            "<cv###>": "v000",
            "<filename>": "bz_av_sh0010_comp_v001"
        }
        
        return self.replace_tokens(template, example_tokens)
    
    def get_render_token_values(self, shot_name_clean, new_version):
        """Get token values dictionary for render path replacement"""
        return {
            "<shotdir>": f"/{shot_name_clean}/",
            "<shotname>": shot_name_clean,
            "<version>": f"{new_version:03d}",
            "<current_version>": "000",  # Default for render paths
            "<v###>": f"v{new_version:03d}",
            "<cv###>": "v000",
            "<filename>": f"{shot_name_clean}_comp_v{new_version:03d}",
            "<ext>": ".exr"
        }

    def replace_render_tokens(self, path_template, token_values, format_type='fusion'):
        """Replace tokens in render path template with actual values"""
        result = path_template
        
        # Replace standard tokens
        for token, value in token_values.items():
            if token in result:
                result = result.replace(token, str(value))
        
        # No frame numbering conversion needed - templates already have correct format
        # Fusion uses 0000, Nuke uses %04d in their respective templates
        
        return result


class OCIOConfigParser:
    """Parser for OCIO configuration files"""

    def __init__(self):
        self.pyocio_available = False
        try:
            import PyOpenColorIO as ocio
            self.ocio = ocio
            self.pyocio_available = True
        except ImportError:
            print("PyOpenColorIO not available - OCIO parsing will be limited")

    def parse_ocio_file(self, ocio_path):
        """Parse OCIO file and extract available colorspaces, displays, and views"""
        if not self.pyocio_available:
            return self._parse_ocio_fallback(ocio_path)

        try:
            config = self.ocio.Config.CreateFromFile(str(ocio_path))

            # Get colorspaces - Updated for modern PyOpenColorIO API
            colorspaces = []
            try:
                # Try modern API first
                for cs in config.getColorSpaces():
                    colorspaces.append(cs.getName())
            except AttributeError:
                try:
                    # Try alternative modern API
                    cs_iter = config.getColorSpaces()
                    for cs in cs_iter:
                        colorspaces.append(cs.getName())
                except:
                    # Fall back to older API if available
                    try:
                        for i in range(config.getNumColorSpaces()):
                            cs = config.getColorSpaceNameByIndex(i)
                            colorspaces.append(cs)
                    except:
                        # If all else fails, use fallback parser
                        return self._parse_ocio_fallback(ocio_path)

            # Get displays and views - Updated for modern API
            displays = {}
            try:
                # Try modern API
                display_names = config.getActiveDisplays().split(',') if hasattr(config, 'getActiveDisplays') else []
                if not display_names or display_names == ['']:
                    # Try getAllDisplays if getActiveDisplays doesn't work
                    if hasattr(config, 'getDisplays'):
                        display_names = list(config.getDisplays())
                    else:
                        display_names = []

                for display_name in display_names:
                    display_name = display_name.strip()
                    if display_name:
                        views = []
                        try:
                            # Get views for this display
                            if hasattr(config, 'getViews'):
                                view_list = config.getViews(display_name)
                                views = list(view_list) if view_list else []
                            displays[display_name] = views
                        except:
                            displays[display_name] = []

            except AttributeError:
                try:
                    # Fall back to older API
                    for i in range(config.getNumDisplays()):
                        display_name = config.getDisplay(i)
                        views = []
                        for j in range(config.getNumViews(display_name)):
                            view_name = config.getView(display_name, j)
                            views.append(view_name)
                        displays[display_name] = views
                except:
                    # Use fallback parser
                    return self._parse_ocio_fallback(ocio_path)

            # Get default working space
            default_working_space = "scene_linear"
            if "scene_linear" in colorspaces:
                default_working_space = "scene_linear"
            elif "ACEScg" in colorspaces:
                default_working_space = "ACEScg"
            elif "linear" in colorspaces:
                default_working_space = "linear"
            elif "ACES - ACES2065-1" in colorspaces:
                default_working_space = "ACES - ACES2065-1"
            elif colorspaces:
                # Find a linear colorspace
                for cs in colorspaces:
                    if "linear" in cs.lower() or "scene" in cs.lower() or "aces" in cs.lower():
                        default_working_space = cs
                        break
                else:
                    default_working_space = colorspaces[0]

            return {
                'success': True,
                'colorspaces': colorspaces,
                'displays': displays,
                'default_working_space': default_working_space
            }

        except Exception as e:
            print(f"Error parsing OCIO file with PyOpenColorIO: {e}")
            return self._parse_ocio_fallback(ocio_path)

    def _parse_ocio_fallback(self, ocio_path):
        """Fallback OCIO parser when PyOpenColorIO is not available"""
        try:
            with open(ocio_path, 'r') as f:
                content = f.read()

            # Basic text parsing for common OCIO structures
            colorspaces = []
            displays = {}

            # Extract colorspaces (simplified parsing)
            cs_pattern = r'^\s*-\s*!<ColorSpace>\s*\n\s*name:\s*(.+?)$'
            cs_matches = re.findall(cs_pattern, content, re.MULTILINE)
            colorspaces = [cs.strip() for cs in cs_matches]

            # Extract displays (simplified parsing)
            display_pattern = r'^\s*(.+?):\s*$\n(?:\s*-\s*(.+?)$\n?)*'
            in_displays_section = False
            lines = content.split('\n')

            current_display = None
            for line in lines:
                line = line.strip()
                if line == 'displays:':
                    in_displays_section = True
                    continue
                elif in_displays_section and line and not line.startswith(' ') and not line.startswith('-'):
                    # End of displays section
                    break
                elif in_displays_section and ':' in line and not line.startswith('-'):
                    current_display = line.replace(':', '').strip()
                    displays[current_display] = []
                elif in_displays_section and line.startswith('-') and current_display:
                    view = line.replace('-', '').strip()
                    displays[current_display].append(view)

            # Set defaults if parsing failed
            if not colorspaces:
                colorspaces = ["scene_linear", "sRGB", "Rec709"]
            if not displays:
                displays = {"ACES": ["Rec.709", "sRGB", "P3-D60"], "sRGB": ["sRGB"]}

            default_working_space = "scene_linear" if "scene_linear" in colorspaces else colorspaces[0]

            return {
                'success': True,
                'colorspaces': colorspaces,
                'displays': displays,
                'default_working_space': default_working_space,
                'note': 'Parsed with fallback method - install PyOpenColorIO for better accuracy'
            }

        except Exception as e:
            print(f"Error parsing OCIO file: {e}")
            return {
                'success': False,
                'error': str(e),
                'colorspaces': ["scene_linear", "sRGB", "Rec709"],
                'displays': {"ACES": ["Rec.709", "sRGB"], "sRGB": ["sRGB"]},
                'default_working_space': "scene_linear"
            }

class FolderStructureManager:
    """Complete fixed folder structure manager"""

    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self.template_file = settings_manager.settings_dir / "folder_structure_template.json"
        self.default_template = {
            "description": "Default folder structure template for VFX shots",
            "folder_structure": {
                "comp": {
                    "description": "Compositing files and renders",
                    "subfolders": {
                        "work": {
                            "description": "Working composition files",
                            "subfolders": {}  # Now supports nesting
                        },
                        "render": {
                            "description": "Final renders",
                            "subfolders": {
                                "final": {
                                    "description": "Approved final renders",
                                    "subfolders": {}
                                },
                                "wip": {
                                    "description": "Work in progress renders",
                                    "subfolders": {}
                                }
                            }
                        },
                        "preview": {
                            "description": "Preview renders and dailies",
                            "subfolders": {}
                        },
                        "elements": {
                            "description": "Individual elements and passes",
                            "subfolders": {}
                        }
                    }
                },
                "plate": {
                    "description": "Original plates and footage",
                    "subfolders": {
                        "original": {
                            "description": "Untouched original footage",
                            "subfolders": {}
                        },
                        "conform": {
                            "description": "Conformed and processed plates",
                            "subfolders": {}
                        },
                        "temp": {
                            "description": "Temporary plate processing",
                            "subfolders": {}
                        }
                    }
                },
                "reference": {
                    "description": "Reference materials and assets",
                    "subfolders": {
                        "images": {
                            "description": "Reference images and stills",
                            "subfolders": {}
                        },
                        "video": {
                            "description": "Reference video clips",
                            "subfolders": {}
                        },
                        "assets": {
                            "description": "3D assets and models",
                            "subfolders": {}
                        }
                    }
                },
                "tracking": {
                    "description": "Camera tracking and matchmove data",
                    "subfolders": {
                        "data": {
                            "description": "Tracking data files",
                            "subfolders": {}
                        },
                        "export": {
                            "description": "Exported tracking information",
                            "subfolders": {}
                        }
                    }
                },
                "roto": {
                    "description": "Rotoscoping and masking work",
                    "subfolders": {
                        "work": {
                            "description": "Work-in-progress roto files",
                            "subfolders": {}
                        },
                        "final": {
                            "description": "Final approved roto shapes",
                            "subfolders": {}
                        }
                    }
                }
            }
        }

    def get_template_file_path(self):
        """Get the path to the folder structure template file"""
        return self.template_file

    def load_folder_template(self):
        """Load folder structure template from JSON file"""
        try:
            if self.template_file.exists():
                with open(self.template_file, 'r') as f:
                    template = json.load(f)
                    if self.validate_template(template):
                        return template
                    else:
                        print(f"Invalid template structure, using defaults")
                        return self.default_template
            else:
                self.save_folder_template(self.default_template)
                print(f"Created default folder structure template: {self.template_file}")
                return self.default_template
        except Exception as e:
            print(f"Error loading folder structure template: {e}")
            return self.default_template

    def save_folder_template(self, template):
        """Save folder structure template to JSON file"""
        try:
            self.template_file.parent.mkdir(parents=True, exist_ok=True)
            template_json = json.dumps(template, indent=2, ensure_ascii=False)
            success, message = write_file_atomically(self.template_file, template_json)
            return success
        except Exception as e:
            print(f"Error saving folder template: {e}")
            return False

    def validate_template(self, template):
        """Validate template structure - now supports recursive nesting"""
        try:
            if not isinstance(template, dict):
                QMessageBox.warning(
                    self, "Invalid Template", 
                    "Template must be a JSON object (dictionary)."
                )
                return False
            
            if 'folder_structure' not in template:
                QMessageBox.warning(
                    self, "Invalid Template", 
                    "Template must contain a 'folder_structure' section.\n\n"
                    "Expected format:\n"
                    "{\n"
                    '  "description": "Template description",\n'
                    '  "folder_structure": { ... }\n'
                    "}"
                )
                return False
            
            if not isinstance(template['folder_structure'], dict):
                return False
            
            def validate_folder_dict(folder_dict, depth=0):
                """Recursively validate folder structure"""
                # Prevent excessive nesting (safety limit)
                if depth > 10:
                    return False
                
                if not isinstance(folder_dict, dict):
                    return False
                
                for folder_name, config in folder_dict.items():
                    # Each folder must have a dict config
                    if not isinstance(config, dict):
                        return False
                    
                    # Config should have description (optional) and subfolders (optional)
                    if 'subfolders' in config:
                        subfolders = config['subfolders']
                        
                        # Subfolders must be a dict (new structure)
                        if not isinstance(subfolders, dict):
                            return False
                        
                        # Recursively validate subfolders
                        if subfolders:  # Only validate if non-empty
                            if not validate_folder_dict(subfolders, depth + 1):
                                return False
                
                return True
            
            # Validate the entire structure
            return validate_folder_dict(template['folder_structure'])
            
        except Exception:
            return False

    def get_folder_list(self, template=None):
            """Get flat list of folders to create - now supports recursive nesting"""
            if template is None:
                template = self.load_folder_template()
            
                return []
            
            folders = []
            
            def add_folders_recursive(folder_dict, parent_path=""):
                """Recursively add folders from nested structure"""
                for folder_name, config in folder_dict.items():
                    current_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
                    folders.append(current_path)
                    
                    subfolders = config.get('subfolders', {})
                    if subfolders and isinstance(subfolders, dict):
                        add_folders_recursive(subfolders, current_path)
            
            folder_structure = template.get('folder_structure', {})
            add_folders_recursive(folder_structure)
            
            return folders

    def create_folder_structure(self, shot_directory, template=None):
        """Create folder structure in shot directory - RECURSIVE VERSION"""
        if template is None:
            template = self.load_folder_template()
                
        created_folders = []
        errors = []
        
        try:
            shot_path = Path(shot_directory)
            
            # Ensure shot directory exists first
            shot_path.mkdir(parents=True, exist_ok=True)
            
            folder_structure = template.get('folder_structure', {})
            
            def create_folders_recursive(folder_dict, parent_path):
                """Recursively create folders from nested structure"""
                for folder_name, config in folder_dict.items():
                    current_path = parent_path / folder_name
                    
                    try:
                        current_path.mkdir(parents=True, exist_ok=True)
                        created_folders.append(str(current_path.relative_to(shot_path)))
                    except Exception as e:
                        errors.append(f"Failed to create {current_path}: {e}")
                        continue
                    
                    # Recursively create subfolders
                    subfolders = config.get('subfolders', {})
                    if subfolders and isinstance(subfolders, dict):
                        create_folders_recursive(subfolders, current_path)
            
            # Start recursive creation
            create_folders_recursive(folder_structure, shot_path)
            
            if errors:
                return False, f"Folder structure created with errors: {'; '.join(errors)}"
            else:
                return True, f"Created {len(created_folders)} folders"
        
        except Exception as e:
            return False, f"Error creating folder structure: {e}"

class CompDeploy:
    def __init__(self):
        self.resolve = resolve
        self.project = None
        self.media_pool = None
        self.settings_manager = SettingsManager()

        if self.resolve:
            self.project_manager = self.resolve.GetProjectManager()
            self.project = self.project_manager.GetCurrentProject()
            if self.project:
                self.media_pool = self.project.GetMediaPool()

    def get_selected_clips(self):
        """Get selected clips from media pool"""
        if not self.media_pool:
            return []

        # Try to get selected clips directly from media pool
        try:
            # Method 1: Try GetSelectedClips if available
            if hasattr(self.media_pool, 'GetSelectedClips'):
                selected_clips = self.media_pool.GetSelectedClips()
                if selected_clips:
                    return selected_clips

            # Method 2: Check current folder for selected clips
            folder = self.media_pool.GetCurrentFolder()
            if folder:
                clips = folder.GetClipList()
                selected_clips = []
                for clip in clips:
                    # Try different ways to check if clip is selected
                    try:
                        if (clip.GetClipProperty("Selected") == "1" or
                            clip.GetClipProperty("Selected") == True or
                            clip.GetClipProperty("Selected") == "True"):
                            selected_clips.append(clip)
                    except:
                        continue

                if selected_clips:
                    return selected_clips

            # Method 3: Get all clips from current folder as fallback
            # (User will need to manually select what they want)
            folder = self.media_pool.GetCurrentFolder()
            if folder:
                return folder.GetClipList()

        except Exception as e:
            print(f"Error getting selected clips: {e}")
            return []

        return []
    
    def create_shot_folder_structure(self, shot_directory, shot_name):
        """Create additional folder structure for a shot based on JSON template"""
        # Check if folder creation is enabled in settings
        enabled = self.settings_manager.get_setting("create_folder_structure")
        
        if not enabled:
            return True, "Folder structure creation disabled in settings"
        
        try:
            success, message = self.settings_manager.folder_manager.create_folder_structure(shot_directory)
            
            if success:
                return True, f"Shot folder structure created for {shot_name}: {message}"
            else:
                return False, f"Failed to create folder structure for {shot_name}: {message}"
        
        except Exception as e:
            return False, f"Error creating folder structure for {shot_name}: {e}"

    def extract_vfx_notes(self, clip):
        """Extract VFX notes from clip metadata - Comments and Description fields only"""
        notes = []

        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print(f"\n=== DEBUG: Scanning for VFX Notes ===")
            print(f"Clip: {clip.GetClipProperty('Clip Name') or 'Unknown'}")

        # Primary: Comments field
        try:
            comments_content = clip.GetClipProperty("Comments")
            if comments_content and str(comments_content).strip():
                comments_text = str(comments_content).strip()
                if len(comments_text) > 2 and comments_text.lower() not in ['n/a', 'na', 'none', 'null', '']:
                    notes.append({
                        'source': 'Comments',
                        'content': comments_text,
                        'clip_name': clip.GetClipProperty("Clip Name") or "Unknown Clip"
                    })

                    if hasattr(self, 'debug_enabled') and self.debug_enabled:
                        print(f"  FOUND NOTE in 'Comments': {comments_text}")
        except Exception as e:
            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print(f"  Comments field error: {e}")

        # Secondary: Description field
        try:
            description_content = clip.GetClipProperty("Description")
            if description_content and str(description_content).strip():
                description_text = str(description_content).strip()
                if len(description_text) > 2 and description_text.lower() not in ['n/a', 'na', 'none', 'null', '']:
                    # Only add if different from Comments to avoid duplicates
                    existing_note = any(note['content'] == description_text for note in notes)
                    if not existing_note:
                        notes.append({
                            'source': 'Description',
                            'content': description_text,
                            'clip_name': clip.GetClipProperty("Clip Name") or "Unknown Clip"
                        })

                        if hasattr(self, 'debug_enabled') and self.debug_enabled:
                            print(f"  FOUND NOTE in 'Description': {description_text}")
        except Exception as e:
            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print(f"  Description field error: {e}")

        # Debug: Show what we found
        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print("Available note fields:")
            for field in ["Comments", "Description"]:
                try:
                    value = clip.GetClipProperty(field)
                    if value and str(value).strip():
                        print(f"  {field}: {value}")
                    else:
                        print(f"  {field}: (empty)")
                except:
                    print(f"  {field}: (not accessible)")

        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print(f"Total notes found: {len(notes)}")
            print("=== END DEBUG ===\n")

        # If no notes found and test notes are enabled, create some test notes
        if len(notes) == 0 and hasattr(self, 'create_test_notes') and self.create_test_notes:
            clip_name = clip.GetClipProperty("Clip Name") or "Unknown Clip"
            test_notes = [
                {
                    'source': 'TEST - Comments',
                    'content': 'Remove wire from stunt performer, paint out safety equipment',
                    'clip_name': clip_name
                },
                {
                    'source': 'TEST - Description',
                    'content': 'Add more energy to this shot - needs crowd reactions',
                    'clip_name': clip_name
                }
            ]

            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print(f"No real notes found - adding {len(test_notes)} test notes")

            notes.extend(test_notes)

        return notes

    def extract_layer_info(self, clip_name):
        """Extract base shot name and layer number from clip name"""
        # Pattern 1: shotname_L01_plate_v000 or shotname_L1_plate_v000
        layer_pattern = r'(.+?)_L(\d+)(.*)'

        match = re.search(layer_pattern, clip_name)

        if match:
            base_name = match.group(1)  # shotname
            layer_num = int(match.group(2))  # 01 or 1
            suffix = match.group(3)  # _plate_v000
            return base_name, layer_num, suffix

        # Pattern 2: If no layer pattern, check for _plate_v000 and extract base
        plate_pattern = r'(.+?)_plate_v(\d{3})'
        match = re.search(plate_pattern, clip_name)

        if match:
            base_name = match.group(1)  # shotname (e.g., pls_sh0010)
            version = match.group(2)    # version number
            return base_name, 1, f"_plate_v{version}"  # Default to layer 1

        # If no recognizable pattern, treat as layer 1
        return clip_name, 1, ""

    def group_clips_by_shot(self, clips):
        """Group clips by base shot name, handling layer patterns"""
        shot_groups = {}

        for clip in clips:
            clip_name = clip.GetClipProperty("Clip Name") or f"Clip_{clip}"
            base_name, layer_num, suffix = self.extract_layer_info(clip_name)

            if base_name not in shot_groups:
                shot_groups[base_name] = []

            shot_groups[base_name].append({
                'clip': clip,
                'layer_num': layer_num,
                'clip_name': clip_name,
                'base_name': base_name,
                'suffix': suffix
            })

        # Sort each group by layer number
        for base_name in shot_groups:
            shot_groups[base_name].sort(key=lambda x: x['layer_num'])

        return shot_groups

    def parse_version_from_path(self, filepath):
        """Extract version number from file path"""
        # Match patterns like v000, v001, etc.
        version_pattern = r'_v(\d{3})'
        match = re.search(version_pattern, filepath)
        if match:
            return int(match.group(1))
        return 0

    def get_clip_properties(self, clip):
        """Get additional clip properties like resolution and frame rate"""
        try:
            width = 1920  # Default values
            height = 1080
            fps = 24.0

            # Debug print to see what properties are available
            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                self.debug_clip_properties(clip)

            # Try multiple property names for resolution
            resolution_props = ["Resolution", "Video Resolution", "Res", "Video Res"]
            for prop in resolution_props:
                try:
                    res = clip.GetClipProperty(prop)
                    if res and "x" in str(res):
                        w, h = str(res).split("x")
                        width = int(w.strip())
                        height = int(h.strip())
                        break
                except:
                    continue

            # Try individual width/height if resolution string not found
            if width == 1920 and height == 1080:  # Still default values
                width_props = ["Width", "Video Width", "H Resolution", "Horizontal Resolution"]
                height_props = ["Height", "Video Height", "V Resolution", "Vertical Resolution"]

                for prop in width_props:
                    try:
                        w = clip.GetClipProperty(prop)
                        if w:
                            width = int(float(w))  # float() first in case it's a decimal
                            break
                    except:
                        continue

                for prop in height_props:
                    try:
                        h = clip.GetClipProperty(prop)
                        if h:
                            height = int(float(h))  # float() first in case it's a decimal
                            break
                    except:
                        continue

            # Try multiple property names for frame rate
            fps_props = ["FPS", "Frame Rate", "Video FPS", "Video Frame Rate", "Framerate"]
            for prop in fps_props:
                try:
                    f = clip.GetClipProperty(prop)
                    if f:
                        # Handle various frame rate formats
                        if isinstance(f, str):
                            # Handle formats like "24", "23.976", "24/1", "24000/1001"
                            if "/" in f:
                                num, den = f.split("/")
                                fps = float(num) / float(den)
                            else:
                                fps = float(f)
                        else:
                            fps = float(f)
                        break
                except:
                    continue

            print(f"Detected properties - Width: {width}, Height: {height}, FPS: {fps}")
            return width, height, fps

        except Exception as e:
            print(f"Error getting clip properties: {e}")
            return 1920, 1080, 24.0

    def get_frame_range(self, clip):
        """Get frame range from clip with improved duration detection"""
        try:
            start_frame = None
            end_frame = None
            duration = None

            # Method 1: Try to get frames directly
            try:
                start_frame = int(clip.GetClipProperty("Start"))
                end_frame = int(clip.GetClipProperty("End"))
                if start_frame is not None and end_frame is not None:
                    return start_frame, end_frame
            except:
                pass

            # Method 2: Try Duration and calculate end frame
            try:
                duration = clip.GetClipProperty("Duration")
                if duration:
                    duration = int(duration)
                    # Use default start frame if not found
                    start_frame = 1001
                    end_frame = start_frame + duration - 1
                    return start_frame, end_frame
            except:
                pass

            # Fallback values - use a reasonable default
            print(f"Warning: Could not determine frame range for clip, using default values")
            return 1001, 1100

        except Exception as e:
            print(f"Error getting frame range: {e}")
            return 1001, 1100

    def collect_all_clip_properties(self, clip):
        """Collect all available clip properties and return as dictionary"""
        properties_data = {}
        
        # Comprehensive list of properties to check
        all_properties = [
            # Basic clip info
            "Clip Name", "File Path", "Resolution", "Video Resolution",
            "Width", "Height", "Video Width", "Video Height",
            "FPS", "Frame Rate", "Video FPS", "Video Frame Rate",
            "Duration", "Frames", "Start", "End",
            "Format", "Codec", "Bit Depth", "PAR", "SAR",
            "H Resolution", "V Resolution", "Reel Name",
            "Timecode", "Start TC", "End TC",

            # Metadata fields that might contain notes
            "Notes", "VFX Notes", "Comments", "Description",
            "Shot Notes", "Director Notes", "VFX Comments",
            "Reel Comments", "File Comments", "Clip Comments",
            "Editorial Notes", "Edit Notes", "Editor Comments",
            "Producer Notes", "Supervisor Notes", "User Comments",
            "Project Comments", "Timeline Comments", "Bin Comments",
            "Technical Notes", "Comp Notes", "Render Notes",
            "Comment", "Note", "Text", "Info", "Details",
            "Remarks", "Instructions", "Brief", "Summary",

            # DaVinci Resolve specific
            "Scene", "Shot", "shoot_scene_take", "Angle", "Camera", "Lens",
            "Shoot Date", "Location", "Tape Name", "Roll",
            "Circle shoot_scene_take", "Good shoot_scene_take", "Synced"
        ]

        # Add User fields
        for i in range(1, 21):
            all_properties.append(f"User{i:02d}")

        # Collect all available properties
        for prop in all_properties:
            try:
                value = clip.GetClipProperty(prop)
                if value is not None and str(value).strip():
                    properties_data[prop] = str(value).strip()
            except Exception:
                # Property not available or accessible
                continue

        return properties_data
    
    def collect_comprehensive_clip_data(self, clip_info, clip_group_index):
        """Collect comprehensive data for a single clip including all metadata"""
        clip = clip_info['clip']
        
        # Get all available properties
        all_properties = self.collect_all_clip_properties(clip)
        
        # Get frame range
        start_frame, end_frame = self.get_frame_range(clip)
        
        # Get clip properties (resolution and fps)
        width, height, fps = self.get_clip_properties(clip)
        
        # Get file path and version info
        clip_path = clip.GetClipProperty("File Path") or ""
        current_version = self.parse_version_from_path(clip_path) if clip_path else 0
        
        # Extract VFX notes
        vfx_notes = self.extract_vfx_notes(clip)
        
        # Build comprehensive clip data
        clip_data = {
            "layer_info": {
                "layer_num": clip_info['layer_num'],
                "original_clip_name": clip_info['clip_name'],
                "base_name": clip_info['base_name'],
                "suffix": clip_info['suffix'],
                "group_index": clip_group_index
            },
            "file_info": {
                "file_path": clip_path,
                "current_version": current_version,
                "file_exists": bool(clip_path and Path(clip_path).exists()) if clip_path else False
            },
            "technical_properties": {
                "resolution": {
                    "width": width,
                    "height": height
                },
                "fps": fps,
                "frame_range": {
                    "start": start_frame,
                    "end": end_frame,
                    "duration": end_frame - start_frame + 1
                }
            },
            "vfx_notes": [
                {
                    "source": note['source'],
                    "content": note['content'],
                    "clip_name": note['clip_name']
                }
                for note in vfx_notes
            ],
            "all_metadata": all_properties,
            "metadata_stats": {
                "total_properties_found": len(all_properties),
                "has_comments": bool(all_properties.get("Comments")),
                "has_description": bool(all_properties.get("Description")),
                "vfx_notes_count": len(vfx_notes)
            }
        }
        
        return clip_data

    def create_fusion_multiple_loaders(self, clip_group, comp_start_frame, comp_end_frame, comp_frame_count, base_shot_name, new_version, path_variable):
        """Create multiple Fusion loader tools for each layer with individual frame ranges"""
        loaders = []

        for i, clip_info in enumerate(clip_group):
            try:
                clip = clip_info['clip']
                layer_num = clip_info['layer_num']
                clip_path = clip.GetClipProperty("File Path")
                original_clip_name = clip_info['clip_name']

                if not clip_path:
                    print(f"Warning: No file path found for clip {original_clip_name}")
                    continue

                # Get individual frame range for this layer
                layer_start_frame, layer_end_frame = self.get_frame_range(clip)
                layer_frame_count = layer_end_frame - layer_start_frame + 1

                # Get current version from the file path
                current_version = self.parse_version_from_path(clip_path)

                # Position loaders horizontally spaced out
                x_pos = 110 + (i * 200)  # Space loaders 200 units apart
                y_pos = 16.5

                # Extract actual folder structure from clip path
                clip_path_obj = Path(clip_path)
                
                # Handle sequence notation like [0996-1048] in the path
                if '[' in clip_path and ']' in clip_path:
                    # Remove sequence notation to get the actual folder structure
                    # e.g., mom_sh0020_input_v000_[0996-1048].exr -> mom_sh0020_input_v000_0996.exr
                    sequence_pattern = r'\[(\d+)-\d+\]'
                    match = re.search(sequence_pattern, clip_path)
                    if match:
                        start_frame_from_path = match.group(1)
                        clean_path = re.sub(sequence_pattern, start_frame_from_path, clip_path)
                        clip_path_obj = Path(clean_path)
                
                # Get the actual folder containing the clip (e.g., "mom_sh0010_input_v000")
                clip_folder = clip_path_obj.parent.name
                
                # Get the parent folder of the clip folder (e.g., "input" instead of assuming "plate")
                parent_folder = clip_path_obj.parent.parent.name
                
                # Get the actual filename without frame number
                clip_filename = clip_path_obj.name
                
                # Extract frame number pattern from actual filename
                # Match patterns like _1089.exr, _0996.exr, etc.
                frame_pattern = re.search(r'_(\d{4})\.exr$', clip_filename)
                if frame_pattern:
                    # Replace the actual frame number with the start frame
                    base_filename = clip_filename.replace(f"_{frame_pattern.group(1)}.exr", f"_{layer_start_frame:04d}.exr")
                else:
                    # Fallback: construct filename based on clip folder name
                    base_filename = f"{clip_folder}_{layer_start_frame:04d}.exr"

                # Create relative path using actual folder structure
                loader_folder = f"{parent_folder}\\\\{clip_folder}"
                
                # Use the path variable instead of hardcoded "Comp:"
                input_relative_path = f"{path_variable.rstrip(':')}:\\\\{loader_folder}\\\\{base_filename}"
                
                # Display layer based on original naming or folder structure
                if f"_L{layer_num:02d}_" in original_clip_name or f"_L{layer_num}_" in original_clip_name:
                    display_layer = f"L{layer_num:02d}"
                else:
                    display_layer = "Main"

                loader_name = f"Loader{i+1}"
                if i == 0:
                    # Primary loader - this one connects to Saver
                    loader_name = "Loader1"

                # Debug output
                if hasattr(self, 'debug_enabled') and self.debug_enabled:
                    print(f"Creating Fusion loader {loader_name}:")
                    print(f"  Original path: {clip_path}")
                    print(f"  Loader folder: {loader_folder}")
                    print(f"  Base filename: {base_filename}")
                    print(f"  Full path: {input_relative_path}")

                loader_tool = f"""{loader_name} = Loader {{
            Clips = {{
                Clip {{
                    ID = "Clip{i+1}",
                    Filename = "{input_relative_path}",
                    FormatID = "OpenEXRFormat",
                    StartFrame = {layer_start_frame},
                    LengthSetManually = true,
                    Length = {layer_frame_count},
                    TrimIn = 0,
                    TrimOut = {layer_frame_count - 1},
                    ExtendFirst = 0,
                    ExtendLast = 0,
                    Loop = 1,
                    AspectMode = 0,
                    Depth = 0,
                    TimeCode = 0,
                    GlobalStart = {layer_start_frame},
                    GlobalEnd = {layer_end_frame}
                }},
            }},
            Outputs = {{
                Output = Output {{
                    SourceOp = "{loader_name}",
                    Source = "Output",
                }},
            }},
            ViewInfo = OperatorInfo {{ Pos = {{ {x_pos}, {y_pos} }} }},
            UserControls = ordered() {{
                LayerInfo = {{
                    INPID_InputControl = "LabelControl",
                    ICS_ControlPage = "File",
                    LINKS_Name = "Layer: {display_layer} ({layer_start_frame}-{layer_end_frame})"
                }}
            }}
        }}"""

                loaders.append(loader_tool)

            except Exception as e:
                print(f"Error creating loader for clip {i}: {e}")
                import traceback
                traceback.print_exc()
                continue

        if not loaders:
            print("Warning: No loaders created - returning empty string")
            return ""

        result = ",\n\t\t".join(loaders)
        return result
    
    def create_fusion_saver_section(self, base_shot_name, new_version, start_frame, end_frame, exr_settings, path_variable):
        """Create the Fusion Saver tool section with enhanced metadata injection using Start Render Scripts and template-based render paths"""
        
        # Check single sequence mode
        single_sequence_mode = self.settings_manager.get_setting("single_sequence_mode")
        metadata_injection = self.settings_manager.get_setting("metadata_injection")
        metadata_field_name = self.settings_manager.get_setting("metadata_field_name") or "shoot_scene_take"
        
        # Position Saver to the right of all loaders
        saver_x_pos = 344.152
        saver_y_pos = 73.2694

        # Extract the actual shot name without the version info
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', base_shot_name)
        if not shot_name_clean or shot_name_clean == base_shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', base_shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = base_shot_name

        # Get render path template and generate actual path
        fusion_render_template = self.settings_manager.get_setting("fusion_render_path")
        render_token_values = self.settings_manager.get_render_token_values(shot_name_clean, new_version)
        
        # Create output path based on mode
        if single_sequence_mode:
            # Use v999 for single sequence - override ALL version-related tokens
            render_token_values["<version>"] = "999"
            render_token_values["<v###>"] = "v999" 
            render_token_values["<filename>"] = f"{shot_name_clean}_comp_v999"
            render_token_values["<sequence_folder>"] = f"{shot_name_clean}_comp_v999"
            render_token_values["<render_filename>"] = f"{shot_name_clean}_comp_v999"
            display_version = "v999"
        else:
            # Use actual version for versioned sequences (already set in render_token_values)
            display_version = f"v{new_version:03d}"

        # Replace shotdir with actual path variable
        render_token_values["<shotdir>"] = f"{path_variable.rstrip(':')}:\\\\"
        
        # Generate the full render path using template
        fusion_render_path = self.settings_manager.replace_render_tokens(fusion_render_template, render_token_values, 'fusion')
        
        # Convert forward slashes to backslashes for Fusion
        fusion_render_path = fusion_render_path.replace('/', '\\\\')

        # Build compression settings based on type
        compression_inputs = f'["OpenEXRFormat.Compression"] = Input {{ Value = {exr_settings["compression"]}, }},'

        # Add quality setting for DWAA/DWAB compression (8 and 9)
        if exr_settings['compression'] in [8, 9]:
            compression_inputs += f'\n\t\t\t\t["OpenEXRFormat.DWACompressionLevel"] = Input {{ Value = {exr_settings["quality"]}, }},'

        # Create metadata injection tools if enabled in single sequence mode
        metadata_tools = ""
        metadata_connection = "Loader1"
        
        if single_sequence_mode and metadata_injection:
            # Proper Start Render Script following documentation guidelines
            start_render_script = r'''-- Start Render Script for SetMetaData node - Extract comp version
    -- Follows Fusion Studio Start Render Script best practices

    -- Error handling wrapper function
    local function safeOperation(func, errorMsg)
        local success, result = pcall(func)
        if not success then
            print("CompDeploy ERROR: " .. errorMsg .. " - " .. tostring(result))
            return false, nil
        end
        return true, result
    end

    -- Extract version from composition filename
    local function extractCompVersion()
        -- In Start Render Scripts, 'comp' is directly available
        if not comp then
            print("CompDeploy: No comp object available")
            return "v001"
        end
        
        local success, compAttrs = pcall(function() return comp:GetAttrs() end)
        if not success or not compAttrs then
            print("CompDeploy: Could not get comp attributes")
            return "v001"
        end
        
        local compPath = compAttrs.COMPS_FileName or ""
        
        if compPath == "" then
            print("CompDeploy: Comp not saved, using default version v001")
            return "v001"
        end
        
        -- Extract filename from full path (handle both / and \\\\\\\\ separators)
        local compName = compPath:match("[^/\\\\\\\\]+$") or ""
        compName = compName:gsub("%.comp$", "")
        
        -- Extract version from comp name (e.g., "shot_comp_v003" -> "v003")
        local version = compName:match("_v(%d%d%d)")
        
        if version then
            local fullVersion = "v" .. version
            print("CompDeploy: Extracted version " .. fullVersion .. " from comp: " .. compName)
            return fullVersion
        else
            print("CompDeploy: Could not extract version from comp name: " .. compName .. ", using v001")
            return "v001"
        end
    end

    -- Main execution with comprehensive error handling
    local success, version = safeOperation(extractCompVersion, "Failed to extract comp version")

    if not success then
        version = "v001"
        print("CompDeploy: Using fallback version v001 due to extraction error")
    end

    -- Store version in tool data for Simple Expression access
    -- This is the recommended approach per Fusion Start Render Script documentation
    self:SetData("compVersion", version)

    -- Additional debug information if needed
    local debugSuccess = safeOperation(function()
        -- Try to get tool name, but don't fail if not available
        local toolName = "SetMetaData_Tool"
        
        -- Try to get tool name if possible (may not work in Start Render context)
        local success, attrs = pcall(function() return self:GetAttrs() end)
        if success and attrs and attrs.TOOLS_Name then
            toolName = attrs.TOOLS_Name
        end
        
        local fieldName = "{metadata_field_name}"  -- Field name is embedded from Python
        
        print("CompDeploy: Tool '" .. toolName .. "' will inject version " .. version .. " into field '" .. fieldName .. "'")
        
        -- Store extraction timestamp for debugging (this should work)
        self:SetData("versionExtractedAt", os.date())
        
        return true
    end, "Failed to store debug information")

    print("CompDeploy: Start Render Script completed - Version " .. version .. " ready for injection")'''

            # SetMetaData tool with Start Render Script and Simple Expression
            # The FieldValue now uses a Simple Expression to read from tool data
            metadata_tool = rf"""comp_version_metadata = Fuse.SetMetaData {{
                NameSet = true,
                Inputs = {{
                    FieldName = Input {{ Value = "{metadata_field_name}", }},
                    FieldValue = Input {{
                        Value = "v000",  -- Default fallback value
                        Expression = "comp.Name:match(\"v%d+\") or \"\"",  -- Direct extraction from comp name
                    }},
                    Input = Input {{
                        SourceOp = "Loader1",
                        Source = "Output",
                    }}
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ {saver_x_pos - 120}, {saver_y_pos - 50} }} }},
                UserControls = ordered() {{
                    MetadataInfo = {{
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "Controls",
                        LINKS_Name = "Auto-extracts comp version: [value FieldValue]",
                    }},
                    CurrentVersion = {{
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "Controls",
                        LINKS_Name = "Extracted Version: [value FieldValue]",
                    }},
                }},
                StartRenderScripts = {{
                    [1] = "{start_render_script.replace(chr(10), chr(92) + 'n').replace(chr(34), chr(92) + chr(34))}",
                }},
            }},
            """
            
            metadata_tools = metadata_tool
            metadata_connection = "comp_version_metadata"

        # Build UserControls based on sequence mode
        if single_sequence_mode:
            # Simplified controls for single sequence mode
            user_controls = f"""SequenceMode = {{
                        LINKS_Name = "Mode: Single Sequence (v999) + Auto Metadata",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    MetadataField = {{
                        LINKS_Name = "Metadata Field: {metadata_field_name}",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    RenderPath = {{
                        LINKS_Name = "Render Path: {fusion_render_path}",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    SOLO = {{
                        LINKS_Name = "Solo",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = "    \\n        function check_selected(tool)\\n            return tool:GetAttrs('TOOLB_Selected')\\n        end\\n\\n        function check_enabled(tool)\\n            return tool:GetAttrs('TOOLB_PassThrough')\\n        end\\n\\n        local comp = fu:GetCurrentComp()\\n        local selectedSavers = comp:GetToolList(true, \\"Saver\\")\\n        local allSavers = comp:GetToolList(false, \\"Saver\\")\\n\\n        comp:StartUndo(\\"Solo Saver\\")\\n        \\n        for _, currentSaver in pairs(allSavers) do\\n            if not check_selected(currentSaver) then\\n                currentSaver:SetAttrs( {{ TOOLB_PassThrough = true }} )\\n            end\\n        end\\n        \\n        for _, sel in pairs(selectedSavers) do\\n            if check_enabled(sel) then\\n                sel:SetAttrs({{ TOOLB_PassThrough = false}})\\n            end\\n        end \\n        comp:EndUndo()\\n    ",
                        ICS_ControlPage = "File",
                    }},
                    ML = {{
                        LINKS_Name = "Make Loader",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = " tool = comp.ActiveTool; comp:RunScript(\\"Scripts:Comp/Saver Tools/LoaderFromSaver.lua\\", tool) ",
                        ICS_ControlPage = "File",
                    }}"""
        else:
            # Full version control for versioned sequences
            user_controls = f"""SequenceMode = {{
                        LINKS_Name = "Mode: Versioned Sequences",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    CompVersion = {{
                        LINKS_Name = "Comp Version: v{new_version:03d}",
                        LINKID_DataType = "Text", 
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    RenderPath = {{
                        LINKS_Name = "Render Path: {fusion_render_path}",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    SOLO = {{
                        LINKS_Name = "Solo",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = "    \\n        function check_selected(tool)\\n            return tool:GetAttrs('TOOLB_Selected')\\n        end\\n\\n        function check_enabled(tool)\\n            return tool:GetAttrs('TOOLB_PassThrough')\\n        end\\n\\n        local comp = fu:GetCurrentComp()\\n        local selectedSavers = comp:GetToolList(true, \\"Saver\\")\\n        local allSavers = comp:GetToolList(false, \\"Saver\\")\\n\\n        comp:StartUndo(\\"Solo Saver\\")\\n        \\n        for _, currentSaver in pairs(allSavers) do\\n            if not check_selected(currentSaver) then\\n                currentSaver:SetAttrs( {{ TOOLB_PassThrough = true }} )\\n            end\\n        end\\n        \\n        for _, sel in pairs(selectedSavers) do\\n            if check_enabled(sel) then\\n                sel:SetAttrs({{ TOOLB_PassThrough = false}})\\n            end\\n        end \\n        comp:EndUndo()\\n    ",
                        ICS_ControlPage = "File",
                    }},
                    ML = {{
                        LINKS_Name = "Make Loader",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = " tool = comp.ActiveTool; comp:RunScript(\\"Scripts:Comp/Saver Tools/LoaderFromSaver.lua\\", tool) ",
                        ICS_ControlPage = "File",
                    }},
                    VersionUP = {{
                        LINKS_Name = "Version UP",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = " tool = comp.ActiveTool; comp:RunScript(\\"Scripts:Support/SaverPlus/ButtonVersionUp.py\\", tool) ",
                        ICS_ControlPage = "File",
                    }},
                    VersionDOWN = {{
                        LINKS_Name = "Version DOWN",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = " tool = comp.ActiveTool; comp:RunScript(\\"Scripts:Support/SaverPlus/ButtonVersionDown.py\\", tool) ",
                        ICS_ControlPage = "File",
                    }},
                    VersionMatch = {{
                        LINKS_Name = "Version Match",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = "           local comp = fusion:GetCurrentComp()\\nlocal selected = comp:GetToolList(true)\\n\\n-- Get _v### from comp name\\nlocal compPath = comp:GetAttrs().COMPS_FileName\\nif not compPath or compPath == \\"\\" then\\n    print(\\"âš ï¸ Comp not saved. Please save the comp first.\\")\\n    return\\nend\\n\\nlocal compName = compPath:match(\\"[^/\\\\\\\\]+$\\"):gsub(\\"%.comp$\\", \\"\\")\\nlocal compVersion = compName:match(\\"_v%d+\\") or \\"_v001\\"\\n\\n-- Get selected Saver\\nlocal saver = nil\\nfor _, tool in pairs(selected) do\\n    if tool.ID == \\"Saver\\" then\\n        saver = tool\\n        break\\n    end\\nend\\n\\nif not saver then\\n    print(\\"âš ï¸ No Saver node selected.\\")\\n    return\\nend\\n\\n-- Get Saver's current path\\nlocal currentPath = saver.Clip[1]\\nif not currentPath or currentPath == \\"\\" then\\n    print(\\"âš ï¸ Saver path is empty.\\")\\n    return\\nend\\n\\n-- Replace all _v### with comp version\\nlocal newPath, n = currentPath:gsub(\\"_v%d+\\", compVersion)\\nif n == 0 then\\n    print(\\"â„¹ï¸ No _v### found in Saver path. No change made.\\")\\n    return\\nend\\n\\n-- Apply path change\\ncomp:StartUndo(\\"Update Saver Version\\")\\nsaver.Clip = newPath\\ncomp:EndUndo(true)\\n\\nprint(\\"âœ… Saver path updated to match comp version:\\")\\nprint(\\"Old:\\", currentPath)\\nprint(\\"New:\\", newPath)",
                        ICS_ControlPage = "File",
                    }},
                    VersionMatchRender = {{
                        LINKS_Name = "Match Version & Render Locally",
                        LINKID_DataType = "Number",
                        INP_Default = 0,
                        INPID_InputControl = "ButtonControl",
                        BTNCS_Execute = "           local comp = fusion:GetCurrentComp()\\nlocal selected = comp:GetToolList(true)\\n\\n-- Get _v### from comp name\\nlocal compPath = comp:GetAttrs().COMPS_FileName\\nif not compPath or compPath == \\"\\" then\\n    print(\\"âš ï¸ Comp not saved. Please save the comp first.\\")\\n    return\\nend\\n\\nlocal compName = compPath:match(\\"[^/\\\\\\\\]+$\\"):gsub(\\"%.comp$\\", \\"\\")\\nlocal compVersion = compName:match(\\"_v%d+\\") or \\"_v001\\"\\n\\n-- Get selected Saver\\nlocal saver = nil\\nfor _, tool in pairs(selected) do\\n    if tool.ID == \\"Saver\\" then\\n        saver = tool\\n        break\\n    end\\nend\\n\\nif not saver then\\n    print(\\"âš ï¸ No Saver node selected.\\")\\n    return\\nend\\n\\n-- Get Saver's current path\\nlocal currentPath = saver.Clip[1]\\nif not currentPath or currentPath == \\"\\" then\\n    print(\\"âš ï¸ Saver path is empty.\\")\\n    return\\nend\\n\\n-- Replace all _v### with comp version\\nlocal newPath, n = currentPath:gsub(\\"_v%d+\\", compVersion)\\nif n == 0 then\\n    print(\\"â„¹ï¸ No _v### found in Saver path. No change made.\\")\\n    return\\nend\\n\\n-- Apply path change\\ncomp:StartUndo(\\"Update Saver Version\\")\\nsaver.Clip = newPath\\ncomp:EndUndo(true)\\n\\nprint(\\"âœ… Saver path updated to match comp version:\\")\\nprint(\\"Old:\\", currentPath)\\nprint(\\"New:\\", newPath)\\n\\n            -- Solo this Saver\\n            local allSavers = comp:GetToolList(false, \\"Saver\\")\\n            for _, s in pairs(allSavers) do\\n                s:SetAttrs({{TOOLB_PassThrough = true}})\\n            end\\n            tool:SetAttrs({{TOOLB_PassThrough = false}})\\n\\nif not tool then\\n\\ttool = comp.ActiveTool\\nend\\n\\nif tool then\\n\\tprint('[LifeSaver] Render Selected ' .. tool.Name)\\n\\tcomp:Render({{Tool = tool}})\\nelse\\n\\tprint('[LifeSaver] Selection Error - Please select a node before running this script.')\\nend",
                        ICS_ControlPage = "File",
                    }}"""

        # Build the saver section
        saver_section = f"""{metadata_tools}Saver1 = Saver {{
                CtrlWZoom = false,
                Inputs = {{
                    ProcessWhenBlendIs00 = Input {{ Value = 0, }},
                    Clip = Input {{
                        Value = Clip {{
                            Filename = "{fusion_render_path}",
                            FormatID = "OpenEXRFormat",
                            Length = 0,
                            Saving = true,
                            TrimIn = 0,
                            ExtendFirst = 0,
                            ExtendLast = 0,
                            Loop = 1,
                            AspectMode = 0,
                            Depth = 0,
                            TimeCode = 0,
                            GlobalStart = {start_frame},
                            GlobalEnd = {end_frame}
                        }},
                    }},
                    OutputFormat = Input {{ Value = FuID {{ "OpenEXRFormat" }}, }},
                    ["OpenEXRFormat.Depth"] = Input {{ Value = {exr_settings['bit_depth']}, }},
                    {compression_inputs}
                    ["OpenEXRFormat.ZipCompressionLevel"] = Input {{ Value = 4, }},
                    Input = Input {{
                        SourceOp = "{metadata_connection}",
                        Source = "Output",
                    }},
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ {saver_x_pos}, {saver_y_pos} }} }},
                UserControls = ordered() {{
                    {user_controls}
                }}
            }}"""

        return saver_section

    def create_fusion_comp(self, clip_group, output_path, exr_settings, comp_name, new_version, width, height, fps, base_shot_name, path_variable, path_value):
        """Create Fusion Studio .comp file content with multiple loaders, metadata injection, and VFX notes"""

        # ... [previous code remains the same until tool count calculation] ...

        # Determine active tool - prioritize in this order: metadata tool, first note, saver
        active_tool = "Saver1"
        if single_sequence_mode and self.settings_manager.get_setting("metadata_injection"):
            active_tool = "comp_version_metadata"
        elif notes_section:
            active_tool = "Note1"

        # Calculate CurrentID based on number of tools
        tool_count = len(clip_group)  # Loaders
        tool_count += 1  # Saver
        if single_sequence_mode and self.settings_manager.get_setting("metadata_injection"):
            tool_count += 1  # SetMetaData tool (simple version)
        tool_count += notes_count  # Notes

        comp_content = f"""Composition {{
            CurrentTime = {comp_start_frame},
            RenderRange = {{ {primary_start_frame}, {primary_end_frame} }},
            GlobalRange = {{ {comp_start_frame}, {comp_end_frame} }},
            CurrentID = {tool_count},
            PlaybackUpdateMode = 0,
            Version = "Fusion Studio 19.1.3 build 5",
            SavedOutputs = 0,
            HeldTools = 0,
            DisabledTools = 0,
            LockedTools = 0,
            AudioOffset = 0,
            Resumable = true,
            OutputClips = {{
                "{output_relative_path}"
            }},
            HiQ = true,
            StereoMode = false,
            FrameFormat = {{
                Width = {width},
                Height = {height},
                Rate = {fps_formatted},
                PixelAspect = {{ 1, 1 }},
                GuideRatio = {guide_ratio:.14f},
                DepthFull = 3,
            }},
            Tools = ordered() {{
                {all_tools}
            }},
            ActiveTool = "{active_tool}",
            Frames = {{
                {{
                    Views = ordered() {{
                        Nodes = MultiView {{
                            FlowView = FlowView {{
                                Flags = {{
                                    AutoHideNavigator = true,
                                    ConnectedSnap = true,
                                    AutoSnap = true,
                                    RemoveRouters = true
                                }},
                            }}
                        }}
                    }}
                }}
            }},
            Prefs = {{
                Comp = {{
                    FrameFormat = {{
                        Width = {width},
                        Height = {height},
                        Rate = {fps_formatted},
                        PixelAspect = {{ 1, 1 }},
                        DepthFull = 3,
                    }},
                    NumberStyles = {{
                        ClipFrame = 2
                    }},
                    Preview = {{
                        GlobalScale = 1,
                    }},
                    Paths = {{
                        Map = {{
                            ["{path_variable}"] = "{path_value.replace(chr(92), '/')}",
                        }},
                    }},
                    DiskCache = {{
                        CacheLoaders = {{
                            Enable = true,
                            DiskCache = true,
                        }},
                    }},
                    Memory = {{
                        FramesAtOnce = 10,
                        Render = {{
                            SimultaneousBranching = true
                        }},
                        Interactive = {{
                            SimultaneousBranching = true,
                        }},
                    }},
                }}
            }}
        }}"""

        return comp_content

    def create_fusion_sticky_notes(self, clip_group, notes_position="top"):
        """Create Fusion StickyNote tools from VFX notes found in clips"""
        sticky_notes = []
        note_counter = 1

        # Collect all notes from all clips in the group
        all_notes = []
        for clip_info in clip_group:
            clip = clip_info['clip']
            clip_notes = self.extract_vfx_notes(clip)

            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print(f"Clip {clip_info['clip_name']}: Found {len(clip_notes)} notes")

            for note in clip_notes:
                note['layer_info'] = f"L{clip_info['layer_num']:02d}"
                all_notes.append(note)

        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print(f"Total notes for StickyNote creation: {len(all_notes)}")
            for i, note in enumerate(all_notes):
                print(f"  Note {i+1}: [{note['layer_info']}] {note['source']}: {note['content'][:50]}...")

        if not all_notes:
            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print("No notes found - returning empty string")
            return ""

        # Position notes based on preference
        if notes_position == "top":
            # Position notes above the loaders
            start_x = 110
            start_y = -100  # Above the loaders
            x_spacing = 220
            y_spacing = 0
        else:  # side
            # Position notes to the right side
            start_x = 600
            start_y = 16.5
            x_spacing = 0
            y_spacing = 150

        for i, note in enumerate(all_notes):
            # Calculate position
            if notes_position == "top":
                x_pos = start_x + (i * x_spacing)
                y_pos = start_y
            else:  # side
                x_pos = start_x
                y_pos = start_y + (i * y_spacing)

            # Format note content with layer and source info
            note_text = f"[{note['layer_info']}] {note['content']}"
            if len(note_text) > 200:
                note_text = note_text[:197] + "..."

            # Escape quotes and special characters for Fusion
            escaped_text = note_text.replace('"', '\\"').replace('\n', '\\n').replace('\r', '')

            # Calculate note size based on content length
            base_width = 200
            base_height = 100

            # Adjust size based on text length
            width = min(base_width + (len(note_text) // 5), 350)
            height = max(base_height, min(base_height + (len(note_text) // 50), 250))

            sticky_note = f"""Note{note_counter} = Note {{
			Inputs = {{
				Comments = Input {{ Value = "{escaped_text}", }},
			}},
			ViewInfo = StickyNoteInfo {{
				Pos = {{ {x_pos}, {y_pos} }},
				Size = {{ {width}, {height} }}
			}},
		}}"""

            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print(f"Created StickyNote {note_counter}: {escaped_text[:50]}...")

            sticky_notes.append(sticky_note)
            note_counter += 1

        result = ",\n\t\t".join(sticky_notes)

        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print(f"Generated {len(sticky_notes)} StickyNotes")
            print("StickyNotes section preview:")
            print(result[:200] + "..." if len(result) > 200 else result)

        return result

    def create_fusion_comp(self, clip_group, output_path, exr_settings, comp_name, new_version, width, height, fps, base_shot_name, path_variable, path_value):
        """Create Fusion Studio .comp file content with multiple loaders, metadata injection, and VFX notes"""

        # Extract the actual shot name without the version info
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', base_shot_name)
        if not shot_name_clean or shot_name_clean == base_shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', base_shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = base_shot_name

        # Get frame ranges from all clips to determine overall comp range
        all_start_frames = []
        all_end_frames = []

        for clip_info in clip_group:
            clip = clip_info['clip']
            start_frame, end_frame = self.get_frame_range(clip)
            all_start_frames.append(start_frame)
            all_end_frames.append(end_frame)

        # Overall comp range encompasses all layers
        comp_start_frame = min(all_start_frames)
        comp_end_frame = max(all_end_frames)

        # Get primary clip info for basic settings
        primary_clip_info = clip_group[0]
        primary_start_frame, primary_end_frame = self.get_frame_range(primary_clip_info['clip'])

        # Format fps - if it's a whole number, don't include decimal
        if fps == int(fps):
            fps_formatted = int(fps)
        else:
            fps_formatted = fps

        # Calculate guide ratio from width and height
        guide_ratio = width / height if height > 0 else 1.77777777777778

        # Create tools section with multiple loaders
        tools_section = self.create_fusion_multiple_loaders(clip_group, comp_start_frame, comp_end_frame, primary_end_frame - primary_start_frame + 1, shot_name_clean, new_version, path_variable)

        # Create Saver section (this will include metadata injection if needed)
        saver_section = self.create_fusion_saver_section(shot_name_clean, new_version, primary_start_frame, primary_end_frame, exr_settings, path_variable)

        # Create VFX Notes as StickyNotes if enabled
        include_notes = self.settings_manager.get_setting("include_vfx_notes")
        notes_section = ""
        notes_count = 0

        if include_notes:
            notes_position = self.settings_manager.get_setting("notes_position")
            notes_section = self.create_fusion_sticky_notes(clip_group, notes_position)
            if notes_section:
                notes_count = notes_section.count("Note")

        # Combine all tools in proper order
        all_tools_parts = []
        
        if tools_section:
            all_tools_parts.append(tools_section)
        
        if saver_section:
            all_tools_parts.append(saver_section)
            
        if notes_section:
            all_tools_parts.append(notes_section)

        all_tools = ",\n\t\t".join(all_tools_parts)

        # Create output clips path using the same logic as saver
        single_sequence_mode = self.settings_manager.get_setting("single_sequence_mode")
        
        if single_sequence_mode:
            saver_folder = f"comp\\\\{shot_name_clean}_comp_v999"
            saver_filename = f"{shot_name_clean}_comp_v999_0000.exr"
        else:
            saver_folder = f"comp\\\\{shot_name_clean}_comp_v{new_version:03d}"
            saver_filename = f"{shot_name_clean}_comp_v{new_version:03d}_0000.exr"

        output_relative_path = f"{path_variable.rstrip(':')}:\\\\{saver_folder}\\\\{saver_filename}"

        # Determine active tool - prioritize in this order: metadata tool, first note, saver
        active_tool = "Saver1"
        if single_sequence_mode and self.settings_manager.get_setting("metadata_injection"):
            active_tool = "comp_version_metadata"
        elif notes_section:
            active_tool = "Note1"

        # Calculate CurrentID based on number of tools
        tool_count = len(clip_group)  # Loaders
        tool_count += 1  # Saver
        if single_sequence_mode and self.settings_manager.get_setting("metadata_injection"):
            tool_count += 2  # CompName + SetMetaData tools
        tool_count += notes_count  # Notes

        comp_content = f"""Composition {{
            CurrentTime = {comp_start_frame},
            RenderRange = {{ {primary_start_frame}, {primary_end_frame} }},
            GlobalRange = {{ {comp_start_frame}, {comp_end_frame} }},
            CurrentID = {tool_count},
            PlaybackUpdateMode = 0,
            Version = "Fusion Studio 19.1.3 build 5",
            SavedOutputs = 0,
            HeldTools = 0,
            DisabledTools = 0,
            LockedTools = 0,
            AudioOffset = 0,
            Resumable = true,
            OutputClips = {{
                "{output_relative_path}"
            }},
            HiQ = true,
            StereoMode = false,
            FrameFormat = {{
                Width = {width},
                Height = {height},
                Rate = {fps_formatted},
                PixelAspect = {{ 1, 1 }},
                GuideRatio = {guide_ratio:.14f},
                DepthFull = 3,
            }},
            Tools = ordered() {{
                {all_tools}
            }},
            ActiveTool = "{active_tool}",
            Frames = {{
                {{
                    Views = ordered() {{
                        Nodes = MultiView {{
                            FlowView = FlowView {{
                                Flags = {{
                                    AutoHideNavigator = true,
                                    ConnectedSnap = true,
                                    AutoSnap = true,
                                    RemoveRouters = true
                                }},
                            }}
                        }}
                    }}
                }}
            }},
            Prefs = {{
                Comp = {{
                    FrameFormat = {{
                        Width = {width},
                        Height = {height},
                        Rate = {fps_formatted},
                        PixelAspect = {{ 1, 1 }},
                        DepthFull = 3,
                    }},
                    NumberStyles = {{
                        ClipFrame = 2
                    }},
                    Preview = {{
                        GlobalScale = 1,
                    }},
                    Paths = {{
                        Map = {{
                            ["{path_variable}"] = "{path_value.replace(chr(92), '/')}",
                        }},
                    }},
                    DiskCache = {{
                        CacheLoaders = {{
                            Enable = true,
                            DiskCache = true,
                        }},
                    }},
                    Memory = {{
                        FramesAtOnce = 10,
                        Render = {{
                            SimultaneousBranching = true
                        }},
                        Interactive = {{
                            SimultaneousBranching = true,
                        }},
                    }},
                }}
            }}
        }}"""

        return comp_content

    def create_fusion_depth_comp(self, clip_group, exr_settings, base_shot_name, new_version, 
                              width, height, fps, path_variable, path_value):
        """Create Fusion comp for depth extraction"""
        
        # Extract clean shot name
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', base_shot_name)
        if not shot_name_clean or shot_name_clean == base_shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', base_shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = base_shot_name
        
        # Get primary clip info
        primary_clip_info = clip_group[0]
        primary_clip = primary_clip_info['clip']
        primary_start_frame, primary_end_frame = self.get_frame_range(primary_clip)
        
        # Get all frame ranges
        all_start_frames = []
        all_end_frames = []
        for clip_info in clip_group:
            start, end = self.get_frame_range(clip_info['clip'])
            all_start_frames.append(start)
            all_end_frames.append(end)
        
        comp_start_frame = min(all_start_frames)
        comp_end_frame = max(all_end_frames)
        
        # Format fps
        fps_formatted = int(fps) if fps == int(fps) else fps
        guide_ratio = width / height if height > 0 else 1.77777777777778
        
        # Create loader section (reuse existing method for primary clip only)
        primary_clip_group = [clip_group[0]]  # Use only primary layer
        loader_section = self.create_fusion_multiple_loaders(
            primary_clip_group, comp_start_frame, comp_end_frame,
            primary_end_frame - primary_start_frame + 1,
            shot_name_clean, new_version, path_variable
        )
        
        # Create DepthMap node
        depth_node = f"""DepthMap1 = DepthMap {{
                Inputs = {{
                    FarLimit = Input {{ Disabled = true, }},
                    NearLimit = Input {{ Disabled = true, }},
                    Gamma = Input {{ Disabled = true, }},
                    TargetDepth = Input {{ Disabled = true, }},
                    Tolerance = Input {{ Disabled = true, }},
                    Softness = Input {{ Disabled = true, }},
                    PostFilter = Input {{ Disabled = true, }},
                    ContractExpand = Input {{ Disabled = true, }},
                    Blur = Input {{ Disabled = true, }},
                    Input = Input {{
                        SourceOp = "Loader1",
                        Source = "Output",
                    }}
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 220.776, 16.8916 }} }},
                Version = 1
            }}"""
        
        # Get render path for depth
        single_sequence_mode = self.settings_manager.get_setting("single_sequence_mode")
        depth_render_template = self.settings_manager.get_setting("fusion_depth_render_path")
        render_token_values = self.settings_manager.get_render_token_values(shot_name_clean, new_version)
        
        if single_sequence_mode:
            render_token_values["<version>"] = "999"
            render_token_values["<v###>"] = "v999"
            render_token_values["<filename>"] = f"{shot_name_clean}_depth_v999"
            display_version = "v999"
        else:
            display_version = f"v{new_version:03d}"
        
        render_token_values["<shotdir>"] = f"{path_variable.rstrip(':')}:\\\\"
        depth_render_path = self.settings_manager.replace_render_tokens(
            depth_render_template, render_token_values, 'fusion'
        ).replace('/', '\\\\')
        
        # Create metadata node and saver (reuse similar pattern from main comp)
        metadata_connection = "DepthMap1"
        metadata_node = ""
        
        if single_sequence_mode and self.settings_manager.get_setting("metadata_injection"):
            metadata_field_name = self.settings_manager.get_setting("metadata_field_name") or "shoot_scene_take"
            
            metadata_node = f"""comp_version_metadata = Fuse.SetMetaData {{
                NameSet = true,
                Inputs = {{
                    FieldName = Input {{ Value = "{metadata_field_name}", }},
                    FieldValue = Input {{
                        Value = "v000",
                        Expression = "comp.Name:match(\\"v%%d+\\") or \\"\\"",
                    }},
                    Input = Input {{
                        SourceOp = "DepthMap1",
                        Source = "Output",
                    }}
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 346.711, 16.8529 }} }},
                UserControls = ordered() {{
                    MetadataInfo = {{
                        LINKS_Name = "Auto-extracts comp version: [value FieldValue]",
                        ICS_ControlPage = "Controls",
                        INPID_InputControl = "LabelControl",
                    }},
                    CurrentVersion = {{
                        LINKS_Name = "Extracted Version: [value FieldValue]",
                        ICS_ControlPage = "Controls",
                        INPID_InputControl = "LabelControl",
                    }}
                }}
            }},
            """
            metadata_connection = "comp_version_metadata"
        
        # Build compression settings
        compression_inputs = f'["OpenEXRFormat.Compression"] = Input {{ Value = {exr_settings["compression"]}, }},'
        if exr_settings['compression'] in [8, 9]:
            compression_inputs += f'\n\t\t\t\t["OpenEXRFormat.DWACompressionLevel"] = Input {{ Value = {exr_settings["quality"]}, }},'
        
        # Create Saver node
        saver_node = f"""{metadata_node}Saver1 = Saver {{
                CtrlWZoom = false,
                Inputs = {{
                    ProcessWhenBlendIs00 = Input {{ Value = 0, }},
                    Clip = Input {{
                        Value = Clip {{
                            Filename = "{depth_render_path}",
                            FormatID = "OpenEXRFormat",
                            Length = 0,
                            Saving = true,
                            TrimIn = 0,
                            ExtendFirst = 0,
                            ExtendLast = 0,
                            Loop = 1,
                            AspectMode = 0,
                            Depth = 0,
                            TimeCode = 0,
                            GlobalStart = {primary_start_frame},
                            GlobalEnd = {primary_end_frame}
                        }},
                    }},
                    OutputFormat = Input {{ Value = FuID {{ "OpenEXRFormat" }}, }},
                    ["OpenEXRFormat.Depth"] = Input {{ Value = {exr_settings['bit_depth']}, }},
                    {compression_inputs}
                    ["OpenEXRFormat.ZipCompressionLevel"] = Input {{ Value = 4, }},
                    Input = Input {{
                        SourceOp = "{metadata_connection}",
                        Source = "Output",
                    }},
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 456.476, 17.2446 }} }},
                UserControls = ordered() {{
                    DepthInfo = {{
                        LINKS_Name = "Depth Extraction Comp",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    RenderPath = {{
                        LINKS_Name = "Render Path: {depth_render_path}",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                }}
            }}"""
        
        # Combine all tools
        all_tools = ",\n\t\t".join([loader_section, depth_node, saver_node])
        
        # Create full comp content
        comp_content = f"""Composition {{
            CurrentTime = {comp_start_frame},
            RenderRange = {{ {primary_start_frame}, {primary_end_frame} }},
            GlobalRange = {{ {comp_start_frame}, {comp_end_frame} }},
            CurrentID = 4,
            PlaybackUpdateMode = 0,
            Version = "Fusion Studio 19.1.3 build 5",
            SavedOutputs = 0,
            HeldTools = 0,
            DisabledTools = 0,
            LockedTools = 0,
            AudioOffset = 0,
            Resumable = true,
            HiQ = true,
            StereoMode = false,
            FrameFormat = {{
                Width = {width},
                Height = {height},
                Rate = {fps_formatted},
                PixelAspect = {{ 1, 1 }},
                GuideRatio = {guide_ratio:.14f},
                DepthFull = 3,
            }},
            Tools = ordered() {{
                {all_tools}
            }},
            ActiveTool = "DepthMap1",
            Prefs = {{
                Comp = {{
                    FrameFormat = {{
                        Width = {width},
                        Height = {height},
                        Rate = {fps_formatted},
                        PixelAspect = {{ 1, 1 }},
                        DepthFull = 3,
                    }},
                    Paths = {{
                        Map = {{
                            ["{path_variable}"] = "{path_value.replace(chr(92), '/')}",
                        }},
                    }},
                }}
            }}
        }}"""
        
        return comp_content


    def create_fusion_mmask_comp(self, clip_group, exr_settings, base_shot_name, new_version,
                                width, height, fps, path_variable, path_value):
        """Create Fusion comp for Magic Mask generation"""
        
        # Extract clean shot name
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', base_shot_name)
        if not shot_name_clean or shot_name_clean == base_shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', base_shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = base_shot_name
        
        # Get primary clip info
        primary_clip_info = clip_group[0]
        primary_clip = primary_clip_info['clip']
        primary_start_frame, primary_end_frame = self.get_frame_range(primary_clip)
        
        # Get all frame ranges
        all_start_frames = []
        all_end_frames = []
        for clip_info in clip_group:
            start, end = self.get_frame_range(clip_info['clip'])
            all_start_frames.append(start)
            all_end_frames.append(end)
        
        comp_start_frame = min(all_start_frames)
        comp_end_frame = max(all_end_frames)
        
        # Format fps
        fps_formatted = int(fps) if fps == int(fps) else fps
        guide_ratio = width / height if height > 0 else 1.77777777777778
        
        # Create loader section (primary clip only)
        primary_clip_group = [clip_group[0]]
        loader_section = self.create_fusion_multiple_loaders(
            primary_clip_group, comp_start_frame, comp_end_frame,
            primary_end_frame - primary_start_frame + 1,
            shot_name_clean, new_version, path_variable
        )
        
        # Create MagicMask node
        import uuid
        cache_uuid = str(uuid.uuid4())
        
        mmask_node = f"""MagicMask1 = MagicMask {{
                Inputs = {{
                    ReferenceTime = Input {{ Disabled = true, }},
                    ProcessedFramesLow = Input {{ Disabled = true, }},
                    ProcessedFramesHigh = Input {{ Disabled = true, }},
                    UseLegacyMagicMask = Input {{ Value = 0, }},
                    Strokes = Input {{
                        Value = MagicMaskStrokes {{
                        }},
                    }},
                    Input = Input {{
                        SourceOp = "Loader1",
                        Source = "Output",
                    }}
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 30.3, 65.1925 }} }},
                CachePath = "/tmp/DiskCache/MagicMaskCache/MagicMask1-{cache_uuid}/0/Cache000000.raw",
                AlgoVersion = 1
            }}"""
        
        # Get render path for mmask
        single_sequence_mode = self.settings_manager.get_setting("single_sequence_mode")
        mmask_render_template = self.settings_manager.get_setting("fusion_mmask_render_path")
        render_token_values = self.settings_manager.get_render_token_values(shot_name_clean, new_version)
        
        if single_sequence_mode:
            render_token_values["<version>"] = "999"
            render_token_values["<v###>"] = "v999"
            render_token_values["<filename>"] = f"{shot_name_clean}_mmask_v999"
            display_version = "v999"
        else:
            display_version = f"v{new_version:03d}"
        
        render_token_values["<shotdir>"] = f"{path_variable.rstrip(':')}:\\\\"
        mmask_render_path = self.settings_manager.replace_render_tokens(
            mmask_render_template, render_token_values, 'fusion'
        ).replace('/', '\\\\')
        
        # Create metadata node and saver
        metadata_connection = "MagicMask1"
        metadata_node = ""
        
        if single_sequence_mode and self.settings_manager.get_setting("metadata_injection"):
            metadata_field_name = self.settings_manager.get_setting("metadata_field_name") or "shoot_scene_take"
            
            metadata_node = f"""comp_version_metadata = Fuse.SetMetaData {{
                NameSet = true,
                Inputs = {{
                    FieldName = Input {{ Value = "{metadata_field_name}", }},
                    FieldValue = Input {{
                        Value = "v000",
                        Expression = "comp.Name:match(\\"v%%d+\\") or \\"\\"",
                    }},
                    Input = Input {{
                        SourceOp = "MagicMask1",
                        Source = "Output",
                    }}
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 163.568, 65.1538 }} }},
                UserControls = ordered() {{
                    MetadataInfo = {{
                        LINKS_Name = "Auto-extracts comp version: [value FieldValue]",
                        ICS_ControlPage = "Controls",
                        INPID_InputControl = "LabelControl",
                    }},
                    CurrentVersion = {{
                        LINKS_Name = "Extracted Version: [value FieldValue]",
                        ICS_ControlPage = "Controls",
                        INPID_InputControl = "LabelControl",
                    }}
                }}
            }},
            """
            metadata_connection = "comp_version_metadata"
        
        # Build compression settings
        compression_inputs = f'["OpenEXRFormat.Compression"] = Input {{ Value = {exr_settings["compression"]}, }},'
        if exr_settings['compression'] in [8, 9]:
            compression_inputs += f'\n\t\t\t\t["OpenEXRFormat.DWACompressionLevel"] = Input {{ Value = {exr_settings["quality"]}, }},'
        
        # Create Saver node - CORRECTED UserControls
        saver_node = f"""{metadata_node}Saver1 = Saver {{
                CtrlWZoom = false,
                Inputs = {{
                    ProcessWhenBlendIs00 = Input {{ Value = 0, }},
                    Clip = Input {{
                        Value = Clip {{
                            Filename = "{mmask_render_path}",
                            FormatID = "OpenEXRFormat",
                            Length = 0,
                            Saving = true,
                            TrimIn = 0,
                            ExtendFirst = 0,
                            ExtendLast = 0,
                            Loop = 1,
                            AspectMode = 0,
                            Depth = 0,
                            TimeCode = 0,
                            GlobalStart = {primary_start_frame},
                            GlobalEnd = {primary_end_frame}
                        }},
                    }},
                    OutputFormat = Input {{ Value = FuID {{ "OpenEXRFormat" }}, }},
                    ["OpenEXRFormat.Depth"] = Input {{ Value = {exr_settings['bit_depth']}, }},
                    {compression_inputs}
                    ["OpenEXRFormat.ZipCompressionLevel"] = Input {{ Value = 4, }},
                    Input = Input {{
                        SourceOp = "{metadata_connection}",
                        Source = "Output",
                    }},
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 273.333, 65.5455 }} }},
                UserControls = ordered() {{
                    MaskInfo = {{
                        LINKS_Name = "Magic Mask Generation Comp",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    RenderPath = {{
                        LINKS_Name = "Render Path: {mmask_render_path}",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                }}
            }}"""
        
        # Combine all tools
        all_tools = ",\n\t\t".join([loader_section, mmask_node, saver_node])
        
        # Create full comp content
        comp_content = f"""Composition {{
            CurrentTime = {comp_start_frame},
            RenderRange = {{ {primary_start_frame}, {primary_end_frame} }},
            GlobalRange = {{ {comp_start_frame}, {comp_end_frame} }},
            CurrentID = 4,
            PlaybackUpdateMode = 0,
            Version = "Fusion Studio 19.1.3 build 5",
            SavedOutputs = 0,
            HeldTools = 0,
            DisabledTools = 0,
            LockedTools = 0,
            AudioOffset = 0,
            Resumable = true,
            HiQ = true,
            StereoMode = false,
            FrameFormat = {{
                Width = {width},
                Height = {height},
                Rate = {fps_formatted},
                PixelAspect = {{ 1, 1 }},
                GuideRatio = {guide_ratio:.14f},
                DepthFull = 3,
            }},
            Tools = ordered() {{
                {all_tools}
            }},
            ActiveTool = "MagicMask1",
            Prefs = {{
                Comp = {{
                    FrameFormat = {{
                        Width = {width},
                        Height = {height},
                        Rate = {fps_formatted},
                        PixelAspect = {{ 1, 1 }},
                        DepthFull = 3,
                    }},
                    Paths = {{
                        Map = {{
                            ["{path_variable}"] = "{path_value.replace(chr(92), '/')}",
                        }},
                    }},
                }}
            }}
        }}"""
        
        return comp_content
    
    def create_fusion_mmask_comp(self, clip_group, exr_settings, base_shot_name, new_version,
                              width, height, fps, path_variable, path_value):
        """Create Fusion comp for Magic Mask generation"""
        
        # Extract clean shot name
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', base_shot_name)
        if not shot_name_clean or shot_name_clean == base_shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', base_shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = base_shot_name
        
        # Get primary clip info
        primary_clip_info = clip_group[0]
        primary_clip = primary_clip_info['clip']
        primary_start_frame, primary_end_frame = self.get_frame_range(primary_clip)
        
        # Get all frame ranges
        all_start_frames = []
        all_end_frames = []
        for clip_info in clip_group:
            start, end = self.get_frame_range(clip_info['clip'])
            all_start_frames.append(start)
            all_end_frames.append(end)
        
        comp_start_frame = min(all_start_frames)
        comp_end_frame = max(all_end_frames)
        
        # Format fps
        fps_formatted = int(fps) if fps == int(fps) else fps
        guide_ratio = width / height if height > 0 else 1.77777777777778
        
        # Create loader section (primary clip only)
        primary_clip_group = [clip_group[0]]
        loader_section = self.create_fusion_multiple_loaders(
            primary_clip_group, comp_start_frame, comp_end_frame,
            primary_end_frame - primary_start_frame + 1,
            shot_name_clean, new_version, path_variable
        )
        
        # Create MagicMask node
        import uuid
        cache_uuid = str(uuid.uuid4())
        
        mmask_node = f"""MagicMask1 = MagicMask {{
                Inputs = {{
                    ReferenceTime = Input {{ Disabled = true, }},
                    ProcessedFramesLow = Input {{ Disabled = true, }},
                    ProcessedFramesHigh = Input {{ Disabled = true, }},
                    UseLegacyMagicMask = Input {{ Value = 0, }},
                    Strokes = Input {{
                        Value = MagicMaskStrokes {{
                        }},
                    }},
                    Input = Input {{
                        SourceOp = "Loader1",
                        Source = "Output",
                    }}
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 272.3, 15.4955 }} }},
                CachePath = "/tmp/DiskCache/MagicMaskCache/MagicMask1-{cache_uuid}/0/Cache000000.raw",
                AlgoVersion = 1
            }}"""
        
        # Get render path for mmask
        single_sequence_mode = self.settings_manager.get_setting("single_sequence_mode")
        mmask_render_template = self.settings_manager.get_setting("fusion_mmask_render_path")
        render_token_values = self.settings_manager.get_render_token_values(shot_name_clean, new_version)
        
        if single_sequence_mode:
            render_token_values["<version>"] = "999"
            render_token_values["<v###>"] = "v999"
            render_token_values["<filename>"] = f"{shot_name_clean}_mmask_v999"
            display_version = "v999"
        else:
            display_version = f"v{new_version:03d}"
        
        render_token_values["<shotdir>"] = f"{path_variable.rstrip(':')}:\\\\"
        mmask_render_path = self.settings_manager.replace_render_tokens(
            mmask_render_template, render_token_values, 'fusion'
        ).replace('/', '\\\\')
        
        # Create metadata node and saver
        metadata_connection = "MagicMask1"
        metadata_node = ""
        
        if single_sequence_mode and self.settings_manager.get_setting("metadata_injection"):
            metadata_field_name = self.settings_manager.get_setting("metadata_field_name") or "shoot_scene_take"
            
            metadata_node = f"""comp_version_metadata = Fuse.SetMetaData {{
                NameSet = true,
                Inputs = {{
                    FieldName = Input {{ Value = "{metadata_field_name}", }},
                    FieldValue = Input {{
                        Value = "v000",
                        Expression = "comp.Name:match(\\"v%%d+\\") or \\"\\"",
                    }},
                    Input = Input {{
                        SourceOp = "MagicMask1",
                        Source = "Output",
                    }}
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 405.568, 15.4568 }} }},
                UserControls = ordered() {{
                    MetadataInfo = {{
                        LINKS_Name = "Auto-extracts comp version: [value FieldValue]",
                        ICS_ControlPage = "Controls",
                        INPID_InputControl = "LabelControl",
                    }},
                    CurrentVersion = {{
                        LINKS_Name = "Extracted Version: [value FieldValue]",
                        ICS_ControlPage = "Controls",
                        INPID_InputControl = "LabelControl",
                    }}
                }}
            }},
            """
            metadata_connection = "comp_version_metadata"
        
        # Build compression settings
        compression_inputs = f'["OpenEXRFormat.Compression"] = Input {{ Value = {exr_settings["compression"]}, }},'
        if exr_settings['compression'] in [8, 9]:
            compression_inputs += f'\n\t\t\t\t["OpenEXRFormat.DWACompressionLevel"] = Input {{ Value = {exr_settings["quality"]}, }},'
        
        # Create Saver node with CORRECT UserControls for Magic Mask
        saver_node = f"""{metadata_node}Saver1 = Saver {{
                CtrlWZoom = false,
                Inputs = {{
                    ProcessWhenBlendIs00 = Input {{ Value = 0, }},
                    Clip = Input {{
                        Value = Clip {{
                            Filename = "{mmask_render_path}",
                            FormatID = "OpenEXRFormat",
                            Length = 0,
                            Saving = true,
                            TrimIn = 0,
                            ExtendFirst = 0,
                            ExtendLast = 0,
                            Loop = 1,
                            AspectMode = 0,
                            Depth = 0,
                            TimeCode = 0,
                            GlobalStart = {primary_start_frame},
                            GlobalEnd = {primary_end_frame}
                        }},
                    }},
                    OutputFormat = Input {{ Value = FuID {{ "OpenEXRFormat" }}, }},
                    ["OpenEXRFormat.Depth"] = Input {{ Value = {exr_settings['bit_depth']}, }},
                    {compression_inputs}
                    ["OpenEXRFormat.ZipCompressionLevel"] = Input {{ Value = 4, }},
                    Input = Input {{
                        SourceOp = "{metadata_connection}",
                        Source = "Output",
                    }},
                }},
                ViewInfo = OperatorInfo {{ Pos = {{ 515.333, 15.8485 }} }},
                UserControls = ordered() {{
                    MaskInfo = {{
                        LINKS_Name = "Magic Mask Generation Comp",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                    RenderPath = {{
                        LINKS_Name = "Render Path: {mmask_render_path}",
                        LINKID_DataType = "Text",
                        INPID_InputControl = "LabelControl",
                        ICS_ControlPage = "File",
                    }},
                }}
            }}"""
        
        # Combine all tools
        all_tools = ",\n\t\t".join([loader_section, mmask_node, saver_node])
        
        # Create full comp content with ordered() wrapper
        comp_content = f"""Composition {{
            CurrentTime = {comp_start_frame},
            RenderRange = {{ {primary_start_frame}, {primary_end_frame} }},
            GlobalRange = {{ {comp_start_frame}, {comp_end_frame} }},
            CurrentID = 4,
            PlaybackUpdateMode = 0,
            Version = "Fusion Studio 19.1.3 build 5",
            SavedOutputs = 0,
            HeldTools = 0,
            DisabledTools = 0,
            LockedTools = 0,
            AudioOffset = 0,
            Resumable = true,
            HiQ = true,
            StereoMode = false,
            FrameFormat = {{
                Width = {width},
                Height = {height},
                Rate = {fps_formatted},
                PixelAspect = {{ 1, 1 }},
                GuideRatio = {guide_ratio:.14f},
                DepthFull = 3,
            }},
            Tools = ordered() {{
                {all_tools}
            }},
            ActiveTool = "MagicMask1",
            Prefs = {{
                Comp = {{
                    FrameFormat = {{
                        Width = {width},
                        Height = {height},
                        Rate = {fps_formatted},
                        PixelAspect = {{ 1, 1 }},
                        DepthFull = 3,
                    }},
                    Paths = {{
                        Map = {{
                            ["{path_variable}"] = "{path_value.replace(chr(92), '/')}",
                        }},
                    }},
                }}
            }}
        }}"""
        
        return comp_content



    # ===================== NUKE GENERATION =====================

    def create_nuke_sticky_notes(self, clip_group, notes_position="top"):
        """Create Nuke StickyNote nodes from VFX notes found in clips"""
        sticky_notes = []
        note_counter = 1

        # Collect all notes from all clips in the group
        all_notes = []
        for clip_info in clip_group:
            clip = clip_info['clip']
            clip_notes = self.extract_vfx_notes(clip)

            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print(f"Clip {clip_info['clip_name']}: Found {len(clip_notes)} notes")

            for note in clip_notes:
                note['layer_info'] = f"L{clip_info['layer_num']:02d}"
                all_notes.append(note)

        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print(f"Total notes for Nuke StickyNote creation: {len(all_notes)}")
            for i, note in enumerate(all_notes):
                print(f"  Note {i+1}: [{note['layer_info']}] {note['source']}: {note['content'][:50]}...")

        if not all_notes:
            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print("No notes found - returning empty string")
            return ""

        # Position notes based on preference
        if notes_position == "top":
            # Position notes above the read nodes
            start_x = 110
            start_y = -120  # Above the read nodes
            x_spacing = 220
            y_spacing = 0
        else:  # side
            # Position notes to the right side
            start_x = 800
            start_y = 16
            x_spacing = 0
            y_spacing = 150

        for i, note in enumerate(all_notes):
            # Calculate position
            if notes_position == "top":
                x_pos = start_x + (i * x_spacing)
                y_pos = start_y
            else:  # side
                x_pos = start_x
                y_pos = start_y + (i * y_spacing)

            # Format note content with layer and source info
            note_text = f"[{note['layer_info']}] {note['content']}"
            if len(note_text) > 200:
                note_text = note_text[:197] + "..."

            # Escape special characters for Nuke TCL - escape brackets properly
            escaped_text = note_text.replace('"', '\\"').replace('\n', '\\n').replace('\r', '').replace('[', '\\[').replace(']', '\\]')

            sticky_note = f"""StickyNote {{
                                inputs 0
                                name StickyNote{note_counter}
                                label "{escaped_text}"
                                note_font_size 11
                                xpos {x_pos}
                                ypos {y_pos}
                                }}"""

            if hasattr(self, 'debug_enabled') and self.debug_enabled:
                print(f"Created Nuke StickyNote {note_counter}: {escaped_text[:50]}...")

            sticky_notes.append(sticky_note)
            note_counter += 1

        result = "\n".join(sticky_notes)

        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print(f"Generated {len(sticky_notes)} Nuke StickyNotes")
            print("Nuke StickyNotes section preview:")
            print(result[:200] + "..." if len(result) > 200 else result)

        return result

    def calculate_nuke_relative_paths(self, nuke_output_template):
        """Calculate relative paths based on Nuke output template structure"""
        # Count the directory depth from shotdir to the nuke script location
        # Remove tokens to analyze the path structure
        template_without_tokens = nuke_output_template.replace('<shotdir>', '').replace('<shotname>', 'shot').replace('<version>', '001').replace('<ext>', '.nk')

        # Split the path and count directories after shotdir
        path_parts = [part for part in template_without_tokens.split('/') if part and part != 'shot_comp_v001.nk']
        directory_depth = len(path_parts)

        # Calculate relative path back to shot directory (without assuming "plate")
        if directory_depth == 1:  # e.g., /comp/script.nk
            relative_path_back = ".."
        elif directory_depth == 2:  # e.g., /comp_work/nuke/script.nk
            relative_path_back = "../.."
        else:
            # Fallback: build path with appropriate number of ../
            relative_path_back = "../" * directory_depth

        # Always use Nuke native #### format
        frame_format = "####"

        return relative_path_back, frame_format

    def create_nuke_read_nodes(self, clip_group, base_shot_name, width, height, nuke_output_template, color_management="aces_1.2"):
        """Create multiple Nuke Read nodes for each layer with adaptive relative paths and color management"""
        read_nodes = []

        # Calculate relative paths based on output template structure
        relative_path_back, _ = self.calculate_nuke_relative_paths(nuke_output_template)

        # Get appropriate colorspaces
        colorspaces = self.get_nuke_colorspaces(color_management)
        read_colorspace = colorspaces['read_colorspace']

        # Find the main layer (L01/L00 or first if no layers) - FIXED LOGIC
        main_layer_index = 0
        for i, clip_info in enumerate(clip_group):
            layer_num = clip_info['layer_num']
            # Priority: L00 > L01 > first layer
            if layer_num == 0:  # L00 has highest priority
                main_layer_index = i
                break
            elif layer_num == 1 and clip_group[main_layer_index]['layer_num'] != 0:  # L01 if no L00
                main_layer_index = i

        # Reorder clip_group so main layer comes last (for proper stack connection to Write node)
        main_clip_info = clip_group[main_layer_index]
        other_clips = [clip_info for i, clip_info in enumerate(clip_group) if i != main_layer_index]
        ordered_clips = other_clips + [main_clip_info]  # Main layer last

        for i, clip_info in enumerate(ordered_clips):
            try:
                clip = clip_info['clip']
                layer_num = clip_info['layer_num']
                clip_path = clip.GetClipProperty("File Path")
                original_clip_name = clip_info['clip_name']

                if not clip_path:
                    print(f"Warning: No file path found for Nuke clip {original_clip_name}")
                    continue

                # Get individual frame range for this layer
                layer_start_frame, layer_end_frame = self.get_frame_range(clip)

                # Get current version from the file path
                current_version = self.parse_version_from_path(clip_path)

                # Position read nodes - main layer in center, others spread out
                is_main_layer = (clip_info == main_clip_info)
                if is_main_layer:
                    # Main layer positioned for vertical alignment with Write
                    x_pos = 344  # Same x as Write node for vertical alignment
                    y_pos = 16
                else:
                    # Other layers spread out horizontally from main position
                    offset = i - len(other_clips)  # Offset from main position
                    x_pos = 344 + (offset * 200)
                    y_pos = 16

                # Extract actual folder structure from clip path
                clip_path_obj = Path(clip_path)
                
                # Handle sequence notation like [0996-1048] in the path
                if '[' in clip_path and ']' in clip_path:
                    # Remove sequence notation to get the actual folder structure
                    # e.g., mom_sh0020_input_v000_[0996-1048].exr -> mom_sh0020_input_v000_0996.exr
                    sequence_pattern = r'\[(\d+)-\d+\]'
                    match = re.search(sequence_pattern, clip_path)
                    if match:
                        start_frame_from_path = match.group(1)
                        clean_path = re.sub(sequence_pattern, start_frame_from_path, clip_path)
                        clip_path_obj = Path(clean_path)
                
                # Get the actual folder containing the clip
                clip_folder = clip_path_obj.parent.name
                
                # Get the parent folder of the clip folder
                parent_folder = clip_path_obj.parent.parent.name
                
                # Get the actual filename without frame number and replace with ####
                clip_filename = clip_path_obj.name
                
                # Extract frame number pattern from actual filename and replace with ####
                frame_pattern = re.search(r'_(\d{4})\.exr$', clip_filename)
                if frame_pattern:
                    read_filename = clip_filename.replace(f"_{frame_pattern.group(1)}.exr", "_####.exr")
                else:
                    # Fallback: construct filename based on clip folder name
                    read_filename = f"{clip_folder}_####.exr"

                # Create relative path using actual folder structure
                read_folder = f"{relative_path_back}/{parent_folder}/{clip_folder}"
                
                # Use relative path format as requested
                input_relative_path = f"{read_folder}/{read_filename}"
                
                # Display layer based on original naming or folder structure
                if f"_L{layer_num:02d}_" in original_clip_name or f"_L{layer_num}_" in original_clip_name:
                    display_layer = f"L{layer_num:02d}"
                else:
                    display_layer = "Main"

                read_name = f"Read{i+1}"

                # Main layer is selected and will connect to Write
                selected = "true" if is_main_layer else "false"

                # Debug output
                if hasattr(self, 'debug_enabled') and self.debug_enabled:
                    print(f"Creating Nuke read node {read_name}:")
                    print(f"  Original path: {clip_path}")
                    print(f"  Read folder: {read_folder}")
                    print(f"  Read filename: {read_filename}")
                    print(f"  Full path: {input_relative_path}")
                    print(f"  Read colorspace: {read_colorspace}")

                read_node = f"""Read {{
                                    inputs 0
                                    file_type exr
                                    file {input_relative_path}
                                    format "{width} {height} 0 0 {width} {height} 1 {base_shot_name}"
                                    first {layer_start_frame}
                                    last {layer_end_frame}
                                    origfirst {layer_start_frame}
                                    origlast {layer_end_frame}
                                    origset true
                                    colorspace {read_colorspace}
                                    version 1
                                    name {read_name}
                                    tile_color 0x9fffff
                                    label "{display_layer} ({layer_start_frame}-{layer_end_frame})"
                                    selected {selected}
                                    xpos {x_pos}
                                    ypos {y_pos}
                                    postage_stamp false
                                    }}"""

                read_nodes.append(read_node)

            except Exception as e:
                print(f"Error creating Nuke read node for clip {i}: {e}")
                import traceback
                traceback.print_exc()
                continue

        if not read_nodes:
            print("Warning: No Nuke read nodes created - returning empty string")
            return "", 0

        # Return the main layer's new index (it's now last)
        new_main_layer_index = len(ordered_clips) - 1

        return "\n".join(read_nodes), new_main_layer_index

    def create_nuke_write_node(self, base_shot_name, new_version, start_frame, end_frame, exr_settings, nuke_output_template, color_management="aces_1.2"):
        """Create the Nuke Write node with TCL-based metadata injection that auto-updates from script filename and template-based render paths"""
        
        # Check single sequence mode and metadata injection settings
        single_sequence_mode = self.settings_manager.get_setting("single_sequence_mode")
        metadata_injection = self.settings_manager.get_setting("metadata_injection")
        metadata_field_name = self.settings_manager.get_setting("metadata_field_name") or "shoot_scene_take"
        
        # Position Write node below and to the right of read nodes
        write_x_pos = 344
        write_y_pos = 100

        # Extract the clean shot name without version info
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', base_shot_name)
        if not shot_name_clean or shot_name_clean == base_shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', base_shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = base_shot_name

        # Get render path template and generate actual path
        nuke_render_template = self.settings_manager.get_setting("nuke_render_path")
        render_token_values = self.settings_manager.get_render_token_values(shot_name_clean, new_version)
        
        # Calculate relative paths based on Nuke output template structure
        relative_path_back, _ = self.calculate_nuke_relative_paths(nuke_output_template)
        
        # Replace shotdir with relative path back to shot directory
        render_token_values["<shotdir>"] = relative_path_back
        
        # Create output path based on mode
        if single_sequence_mode:
            # Use v999 for single sequence - override ALL version-related tokens
            render_token_values["<version>"] = "999"
            render_token_values["<v###>"] = "v999" 
            render_token_values["<filename>"] = f"{shot_name_clean}_comp_v999"
            render_token_values["<sequence_folder>"] = f"{shot_name_clean}_comp_v999"
            render_token_values["<render_filename>"] = f"{shot_name_clean}_comp_v999"
            display_version = "v999"
            # Use special Write node name so callbacks will skip it
            write_node_name = "Write_v999_EXR"
        else:
            # Use actual version for versioned sequences (already set in render_token_values)
            display_version = f"v{new_version:03d}"
            # Use standard Write node name so callbacks will work
            write_node_name = "Write_EXR"

        # Generate the full render path using template
        nuke_render_path = self.settings_manager.replace_render_tokens(nuke_render_template, render_token_values, 'nuke')

        # Map compression values to Nuke compression names
        compression_map = {
            0: "none", 1: "RLE", 2: "Zip", 3: "Zip", 4: "PIZ",
            5: "PXR24", 6: "B44", 7: "B44A", 8: "DWAA", 9: "DWAB"
        }

        compression_name = compression_map.get(exr_settings['compression'], 'PIZ')

        # Map bit depth values
        bit_depth_map = {1: "16 bit half", 2: "32 bit float"}
        bit_depth_name = bit_depth_map.get(exr_settings['bit_depth'], "16 bit half")

        # Add DWA quality if using DWAA/DWAB
        dwa_quality_line = ""
        if exr_settings['compression'] in [8, 9]:
            dwa_quality_line = f"\n dw_compression_level {exr_settings['quality']}"

        # Get appropriate colorspaces
        colorspaces = self.get_nuke_colorspaces(color_management)
        write_colorspace = colorspaces['write_colorspace']

        # Add TCL-based metadata injection node if enabled in single sequence mode
        metadata_node = ""
        metadata_connection_input = ""
        
        if single_sequence_mode and metadata_injection:
            # Create ModifyMetaData node with TCL expression that auto-extracts version from script filename
            # This TCL expression extracts the last 4 characters from the script name (e.g., "v003" from "shot_comp_v003.nk")
            tcl_expression = r'"[string range [file rootname [file tail [value root.name]]] end-3 end]"'
            
            metadata_node = f"""ModifyMetaData {{
                                metadata {{
                                {{set exr/{metadata_field_name} {tcl_expression}}}
                                }}
                                name MetaData_CompVersion
                                label "[string range [file rootname [file tail [value root.name]]] end-3 end]"
                                selected false
                                xpos {write_x_pos}
                                ypos {write_y_pos - 5}
                                }}

                                """
            # Write node will connect to metadata node instead of directly to read
            metadata_connection_input = f"""{{
    inputs 1
    """
            write_y_pos += 100  # Move Write node down to make room for metadata node
        else:
            # Standard connection directly to read node
            metadata_connection_input = f"""{{
    inputs 1
    """

        # Build label text based on mode
        if single_sequence_mode:
            label_text = f"v999 \[value channels]\n\[value file_type] \[value compression]\n\[value datatype]"
        else:
            label_text = f"[string range [file rootname [file tail [value root.name]]] end-3 end] \[value channels]\n\[value file_type] \[value compression]\n\[value datatype]"

        # Debug output for colorspace
        if hasattr(self, 'debug_enabled') and self.debug_enabled:
            print(f"Creating Nuke write node:")
            print(f"  Write colorspace: {write_colorspace}")
            print(f"  Color management: {color_management}")
            print(f"  Render path: {nuke_render_path}")

        write_node = f"""{metadata_node}Write {metadata_connection_input}
            file {nuke_render_path}
            file_type exr
            datatype "{bit_depth_name}"
            compression {compression_name}{dwa_quality_line}
            metadata "all metadata"
            first_part rgba
            autocrop false
            create_directories true
            colorspace {write_colorspace}
            name {write_node_name}
             tile_color 0xff9455ff
            label "{label_text}"
            selected false
            xpos {write_x_pos}
            ypos {write_y_pos}
            }}"""

        return write_node

    def get_nuke_colorspaces(self, color_management="aces_1.2"):
        """Get appropriate colorspaces for different Nuke node types"""
        if color_management == "nuke_default":
            return {
                'read_colorspace': "Rec709",
                'write_colorspace': "Rec709", 
                'working_colorspace': "linear"
            }
        elif color_management == "custom_ocio":
            plate_colorspace = self.settings_manager.get_setting("custom_ocio_plate_colorspace") or "ACEScct"
            working_colorspace = self.settings_manager.get_setting("custom_ocio_working_space") or "scene_linear"
            return {
                'read_colorspace': plate_colorspace,      # Use plate colorspace for Read nodes
                'write_colorspace': plate_colorspace,     # Use plate colorspace for Write nodes  
                'working_colorspace': working_colorspace  # Use working colorspace for internal processing
            }
        else:  # aces_1.2
            return {
                'read_colorspace': "scene_linear",
                'write_colorspace': "scene_linear",
                'working_colorspace': "scene_linear"
            }

    def create_nuke_root_node_with_callbacks(self, shot_name_clean, script_start_frame, script_end_frame, 
                                       width, height, fps, color_management="aces_1.2", 
                                       project_dir_line=""):
        """Create Root node with optional simple callback for Write_EXR only (MetaData uses TCL)"""
        
        # Simple callback that only targets Write_EXR nodes (not Write_v999_EXR)
        # No metadata callback needed since ModifyMetaData node uses TCL expressions
        simple_callback = "import nuke; import os; import re; sn=nuke.root().name(); bn=os.path.basename(sn) if sn else ''; vm=re.search(r'_v(\\\\d\\\\d\\\\d)', bn); sv=vm.group(1) if vm else None; wn=nuke.toNode('Write_EXR'); wn\\['file'\\].setValue(re.sub(r'_v\\\\d\\\\d\\\\d', '_v'+sv, wn\\['file'\\].value())) if wn and sv and wn\\['file'\\].value() else None"

        # Build color management lines
        if color_management == "nuke_default":
            color_management_lines = f"""
    colorManagement Nuke
    OCIO_config aces_1.2
    workingSpaceLUT linear
    int8Lut sRGB
    int16Lut sRGB
    logLut Cineon
    floatLut linear"""
        elif color_management == "custom_ocio":
            custom_ocio_config = self.settings_manager.get_setting("custom_ocio_config")
            working_space = self.settings_manager.get_setting("custom_ocio_working_space") or "scene_linear"

            if custom_ocio_config:
                abs_config_path = os.path.abspath(custom_ocio_config).replace('\\', '/')
                color_management_lines = f"""
    colorManagement OCIO
    OCIO_config custom
    customOCIOConfigPath "{abs_config_path}"
    defaultViewerLUT "OCIO LUTs"
    workingSpaceLUT {working_space}
    int8Lut matte_paint
    int16Lut texture_paint
    logLut compositing_log
    floatLut {working_space}"""
            else:
                color_management_lines = f"""
    colorManagement OCIO
    OCIO_config aces_1.2
    defaultViewerLUT "OCIO LUTs"
    workingSpaceLUT scene_linear
    int8Lut matte_paint
    int16Lut texture_paint
    logLut compositing_log
    floatLut scene_linear"""
        else:  # aces_1.2
            color_management_lines = f"""
    colorManagement OCIO
    OCIO_config aces_1.2
    defaultViewerLUT "OCIO LUTs"
    workingSpaceLUT scene_linear
    int8Lut matte_paint
    int16Lut texture_paint
    logLut compositing_log
    floatLut scene_linear"""

        root_node = f"""Root {{
    inputs 0
    name Root{project_dir_line}
    frame {script_start_frame}
    first_frame {script_start_frame}
    last_frame {script_end_frame}
    lock_range true
    format "{width} {height} 0 0 {width} {height} 1 {shot_name_clean}"
    proxy_type scale
    proxy_format "1024 778 0 0 1024 778 1 1K_Super_35(full-ap)"{color_management_lines}
    fps {fps}
    onScriptLoad "{simple_callback}"
    onScriptSave "{simple_callback}"
    }}"""

        return root_node

    def create_nuke_script(self, clip_group, output_path, exr_settings, script_name, new_version, 
                     width, height, fps, base_shot_name, path_variable, path_value, 
                     color_management="aces_1.2"):
        """Create Nuke .nk script content with enhanced single sequence mode support"""

        # Extract the clean shot name without version info
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', base_shot_name)
        if not shot_name_clean or shot_name_clean == base_shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', base_shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = base_shot_name

        # Get frame ranges from all clips to determine overall script range
        all_start_frames = []
        all_end_frames = []

        for clip_info in clip_group:
            clip = clip_info['clip']
            start_frame, end_frame = self.get_frame_range(clip)
            all_start_frames.append(start_frame)
            all_end_frames.append(end_frame)

        script_start_frame = min(all_start_frames)
        script_end_frame = max(all_end_frames)

        # Get primary clip info for basic settings
        primary_clip_info = clip_group[0]
        primary_clip = primary_clip_info['clip']
        primary_start_frame, primary_end_frame = self.get_frame_range(primary_clip)

        # Create script header
        nuke_version = "15.1v4"
        script_header = f"""#! C:/Program Files/Nuke{nuke_version}/nuke-{nuke_version}.exe -nx
            version {nuke_version.replace('v', ' v')}
            define_window_layout_xml {{<?xml version="1.0" encoding="UTF-8"?>
            <layout version="1.0">
            <window x="0" y="0" w="1920" h="1080" screen="0">
                <splitter orientation="1">
                <split size="1536"/>
                <dock id="" hideTitles="1" activePageId="Viewer.1">
                    <page id="Viewer.1"/>
                </dock>
                <split size="384"/>
                <dock id="" activePageId="DAG.1" focus="true">
                    <page id="DAG.1"/>
                    <page id="Curve Editor.1"/>
                    <page id="DopeSheet.1"/>
                </dock>
                </splitter>
            </window>
            </layout>
            }}"""

        # Create read nodes
        nuke_output_template = self.settings_manager.get_setting("nuke_output_path")
        read_nodes_section, main_layer_index = self.create_nuke_read_nodes(
            clip_group, shot_name_clean, width, height, nuke_output_template, color_management
        )

        # Create write node with proper naming and metadata injection
        write_node_section = self.create_nuke_write_node(
            shot_name_clean, new_version, primary_start_frame, primary_end_frame, 
            exr_settings, nuke_output_template, color_management
        )

        # Create VFX Notes as StickyNotes if enabled
        include_notes = self.settings_manager.get_setting("include_vfx_notes")
        notes_section = ""
        if include_notes:
            notes_position = self.settings_manager.get_setting("notes_position")
            notes_section = self.create_nuke_sticky_notes(clip_group, notes_position)

        # Create Viewer node with proper viewer process handling
        if color_management == "custom_ocio":
            custom_viewer_process = self.settings_manager.get_setting("custom_ocio_viewer_process")
            if custom_viewer_process:
                viewer_node_section = f"""Viewer {{
                    frame {script_start_frame}
                    frame_range {script_start_frame}-{script_end_frame}
                    viewerProcess "{custom_viewer_process}"
                    name Viewer1
                    xpos 499
                    ypos 204
                    hide_input true
                    }}"""
            else:
                viewer_node_section = f"""Viewer {{
                    frame {script_start_frame}
                    frame_range {script_start_frame}-{script_end_frame}
                    name Viewer1
                    xpos 499
                    ypos 204
                    hide_input true
                    }}"""
        else:
            if color_management == "nuke_default":
                viewer_process = "rec709"
            else:  # aces_1.2
                viewer_process = "Rec.709 (ACES)"

            viewer_node_section = f"""Viewer {{
                frame {script_start_frame}
                frame_range {script_start_frame}-{script_end_frame}
                viewerProcess "{viewer_process}"
                name Viewer1
                xpos 499
                ypos 204
                hide_input true
                }}"""

        # Create Root node with enhanced callbacks
        project_dir_line = ' project_directory "\\[python \\{nuke.script_directory()\\}]"'
        root_node = self.create_nuke_root_node_with_callbacks(
            shot_name_clean, script_start_frame, script_end_frame, 
            width, height, fps, color_management, project_dir_line
        )

        # Combine all sections in proper order
        script_sections = [script_header, root_node]

        # Add VFX notes first (if any)
        if notes_section:
            script_sections.append(notes_section)

        # Add read nodes
        if read_nodes_section:
            script_sections.append(read_nodes_section)

        # Add write node (includes metadata node if in single sequence mode)
        if write_node_section:
            script_sections.append(write_node_section)

        # Add viewer node last
        if viewer_node_section:
            script_sections.append(viewer_node_section)

        script_content = "\n".join(script_sections)
        return script_content

    # ===================== SHARED UTILITIES =====================

    def extract_path_components(self, clip_path, shot_name):
        """Extract various path components for token replacement"""
        source_path = Path(clip_path)

        # Navigate up from the plate version folder to find the shot folder
        # Example path: ####_ProjectName/comp/bz_av/bz_av_sh0020/plate/bz_av_sh0020_L01_plate_v000/file.exr
        current_dir = source_path.parent  # bz_av_sh0020_L01_plate_v000
        plate_parent = current_dir.parent  # plate
        shot_dir = plate_parent.parent     # bz_av_sh0020 (the shot directory)

        # Extract scene and project from path structure
        # Assuming structure like: project/scene/shot/plate/version/file.exr
        scene_name = shot_dir.parent.name if shot_dir.parent else "unknown_scene"
        project_name = shot_dir.parent.parent.name if shot_dir.parent and shot_dir.parent.parent else "unknown_project"

        return {
            'shot_dir': shot_dir,
            'scene_name': scene_name,
            'project_name': project_name
        }

    def determine_path_variable(self, path_template, shot_dir):
        """Determine what path variable to use based on template structure"""
        # If template uses <shotdir>, use Shot: as the variable pointing to the shot directory
        if "<shotdir>" in path_template:
            return "Shot:", str(shot_dir)
        else:
            # Fallback to Comp: for backward compatibility, pointing to shot directory
            return "Comp:", str(shot_dir)

    def find_next_available_version(self, base_path, shot_name, file_format='fusion'):
        """Find the next available version number starting from v000 for specified format"""
        version = 0

        while version <= 999:
            # Get the appropriate path template based on format
            if file_format == 'fusion':
                path_template = self.settings_manager.get_setting("fusion_output_path")
            elif file_format == 'fusion_depth':
                path_template = self.settings_manager.get_setting("fusion_depth_output_path")
            elif file_format == 'fusion_mmask':
                path_template = self.settings_manager.get_setting("fusion_mmask_output_path")
            else:  # nuke
                path_template = self.settings_manager.get_setting("nuke_output_path")

            # Extract path components for token replacement
            components = self.extract_path_components(str(base_path), shot_name)
            shot_dir = components['shot_dir']

            # Determine extension
            if file_format == 'nuke':
                extension = ".nk"
            else:
                extension = ".comp"

            # Define token values for this version
            token_values = {
                "<shotdir>": f"/{shot_name}/",
                "<shotname>": shot_name,
                "<version>": f"{version:03d}",
                "<current_version>": "000",
                "<v###>": f"v{version:03d}",
                "<cv###>": "v000",
                "<filename>": f"{shot_name}_v{version:03d}",
                "<ext>": extension
            }

            # Replace tokens in template
            output_path_str = self.settings_manager.replace_tokens(path_template, token_values)

            # Handle relative shotdir path
            if output_path_str.startswith(f"/{shot_name}/"):
                output_path_str = output_path_str.replace(f"/{shot_name}/", f"{shot_dir}/")

            test_path = Path(output_path_str)

            # If file doesn't exist, this version is available
            if not test_path.exists():
                return version

            version += 1

        return 999

    def create_output_path(self, clip_path, shot_name, current_version, file_format='fusion', overwrite_existing=False):
        """Create output path using user-defined template with version control for specified format"""
        
        # Get appropriate path template and extension based on format
        if file_format == 'fusion':
            path_template = self.settings_manager.get_setting("fusion_output_path")
            extension = ".comp"
        elif file_format == 'fusion_depth':
            path_template = self.settings_manager.get_setting("fusion_depth_output_path")
            extension = ".comp"
        elif file_format == 'fusion_mmask':
            path_template = self.settings_manager.get_setting("fusion_mmask_output_path")
            extension = ".comp"
        elif file_format == 'nuke':
            path_template = self.settings_manager.get_setting("nuke_output_path")
            extension = ".nk"
        else:
            path_template = self.settings_manager.get_setting("fusion_output_path")
            extension = ".comp"

        # Extract path components
        components = self.extract_path_components(clip_path, shot_name)
        shot_dir = components['shot_dir']

        # Extract the clean shot name without version info
        shot_name_clean = re.sub(r'_[^_]*_v\d{3}$', '', shot_name)
        if not shot_name_clean or shot_name_clean == shot_name:
            shot_match = re.match(r'([^_]+_[^_]+_[^_]+)', shot_name)
            if shot_match:
                shot_name_clean = shot_match.group(1)
            else:
                shot_name_clean = shot_name

        # Determine path variable for this template
        if file_format in ['fusion', 'fusion_depth', 'fusion_mmask']:
            if "<shotdir>" in path_template:
                path_variable, path_value = "Shot:", str(shot_dir)
            else:
                path_variable, path_value = "Comp:", str(shot_dir)
        else:  # nuke
            if "<shotdir>" in path_template:
                path_variable, path_value = "SHOTDIR", str(shot_dir)
            else:
                path_variable, path_value = "SHOT", str(shot_dir)

        # Determine version number based on overwrite setting
        if overwrite_existing:
            new_version = 0
        else:
            new_version = self.find_next_available_version(clip_path, shot_name_clean, file_format)

        # Create filename - templates now have the correct suffix built in
        # We don't need to add a suffix here since it's in the template
        base_filename = f"{shot_name_clean}_v{new_version:03d}"

        # For <shotdir> token, create relative path from the clean shot name
        relative_shot_dir = f"/{shot_name_clean}/"

        # Define token values using clean shot name
        token_values = {
            "<shotdir>": relative_shot_dir,
            "<shotname>": shot_name_clean,
            "<version>": f"{new_version:03d}",
            "<current_version>": f"{current_version:03d}",
            "<v###>": f"v{new_version:03d}",
            "<cv###>": f"v{current_version:03d}",
            "<filename>": base_filename,
            "<ext>": extension
        }

        # Replace tokens in template
        output_path_str = self.settings_manager.replace_tokens(path_template, token_values)

        # If the path starts with a relative shotdir, make it relative to the actual shot directory
        if output_path_str.startswith(f"/{shot_name_clean}/"):
            output_path_str = output_path_str.replace(f"/{shot_name_clean}/", f"{shot_dir}/")
        elif output_path_str.startswith(f"{relative_shot_dir}"):
            output_path_str = output_path_str.replace(relative_shot_dir, f"{shot_dir}/")

        output_path = Path(output_path_str)

        # Extract the actual base filename from the final path for return
        actual_base_filename = output_path.stem  # Gets filename without extension

        return output_path, actual_base_filename, path_variable, path_value, new_version


    def create_shot_folder_structure(self, shot_directory, shot_name):
        """Create additional folder structure for a shot based on JSON template"""
        if not self.settings_manager.get_setting("create_folder_structure"):
            return True, "Folder structure creation disabled in settings"
        
        try:
            # Use the folder structure manager to create folders
            success, message = self.settings_manager.folder_manager.create_folder_structure(shot_directory)
            
            if success:
                return True, f"Shot folder structure created for {shot_name}: {message}"
            else:
                return False, f"Failed to create folder structure for {shot_name}: {message}"
        
        except Exception as e:
            return False, f"Error creating folder structure for {shot_name}: {e}"

    def process_selected_clips(self, exr_settings, debug_enabled=False, create_test_notes=False):
        """Process all selected clips and create comp files, grouping by shot name with folder structure creation"""
        self.debug_enabled = debug_enabled
        self.create_test_notes = create_test_notes
        selected_clips = self.get_selected_clips()

        if not selected_clips:
            return False, "No clips selected in media pool"

        # Group clips by shot name (handling layer patterns)
        shot_groups = self.group_clips_by_shot(selected_clips)

        if not shot_groups:
            return False, "No valid shot groups found"

        results = []
        results.append(f"Found {len(shot_groups)} shot group(s) to process:")

        # Show grouping information
        for base_name, clip_group in shot_groups.items():
            layer_names = [f"L{clip_info_item['layer_num']:02d}" for clip_info_item in clip_group]
            results.append(f"  - {base_name}: {', '.join(layer_names)} ({len(clip_group)} layers)")

        results.append("")  # Empty line for readability

        # Check folder structure creation setting
        create_folders = self.settings_manager.get_setting("create_folder_structure")
        if create_folders:
            template = self.settings_manager.folder_manager.load_folder_template()
            folder_list = self.settings_manager.folder_manager.get_folder_list(template)
            results.append(f"Folder structure will be created: {len(folder_list)} folders per shot")
            if debug_enabled:
                results.append(f"   Folders: {', '.join(folder_list)}")
            results.append("")

        # Check for VFX notes across all clips
        include_notes = self.settings_manager.get_setting("include_vfx_notes")
        total_notes_found = 0

        if include_notes:
            for base_name, clip_group in shot_groups.items():
                shot_notes_count = 0
                for clip_info_item in clip_group:
                    clip_notes = self.extract_vfx_notes(clip_info_item['clip'])
                    shot_notes_count += len(clip_notes)

                if shot_notes_count > 0:
                    results.append(f"{base_name}: Found {shot_notes_count} VFX note(s)")
                    total_notes_found += shot_notes_count

            if total_notes_found > 0:
                results.append(f"Total VFX notes found: {total_notes_found}")
                results.append("")

        # Check which formats to generate
        generate_fusion = self.settings_manager.get_setting("generate_fusion")
        generate_nuke = self.settings_manager.get_setting("generate_nuke")
        generate_fusion_depth = self.settings_manager.get_setting("generate_fusion_depth")
        generate_fusion_mmask = self.settings_manager.get_setting("generate_fusion_mmask")

        if not (generate_fusion or generate_nuke or generate_fusion_depth or generate_fusion_mmask):
            return False, "No output formats selected! Please enable Fusion and/or Nuke generation."

        formats_info = []
        if generate_fusion:
            formats_info.append("Fusion Studio (.comp)")
        if generate_nuke:
            # Add color management info for Nuke
            color_management = self.settings_manager.get_setting("nuke_color_management")
            if color_management == "aces_1.2":
                color_info = "ACES 1.2"
            elif color_management == "custom_ocio":
                custom_config = self.settings_manager.get_setting("custom_ocio_config")
                if custom_config:
                    config_name = Path(custom_config).stem
                    color_info = f"Custom OCIO ({config_name})"
                else:
                    color_info = "Custom OCIO (Not Set)"
            else:
                color_info = "Nuke Default"
            formats_info.append(f"Nuke (.nk) - {color_info}")
        if generate_fusion_depth:
            formats_info.append("Fusion Depth (.comp)")
        if generate_fusion_mmask:
            formats_info.append("Fusion Magic Mask (.comp)")

        results.append(f"Generating: {', '.join(formats_info)}")
        results.append("")

        # Initialize report data collection
        shot_groups_data = {}
        generation_results = {
            'formats_generated': formats_info,
            'exr_settings': exr_settings,
            'vfx_notes_included': include_notes,
            'overwrite_existing': self.settings_manager.get_setting("overwrite_existing"),
            'color_management': self.settings_manager.get_setting("nuke_color_management") if generate_nuke else None,
            'folder_structure_created': create_folders
        }

        # Process each shot group
        for base_name, clip_group in shot_groups.items():
            try:
                # Use primary clip (first in group) for main properties
                primary_clip_info = clip_group[0]
                primary_clip = primary_clip_info['clip']

                # Get clip properties with error handling
                clip_path = primary_clip.GetClipProperty("File Path")

                if not clip_path:
                    results.append(f"{base_name}: No file path found for primary clip")
                    continue

                # Show the actual clip path being analyzed
                results.append(f"{base_name}: Analyzing path: {clip_path}")

                # Extract path components to show how <shotdir> is determined
                components = self.extract_path_components(clip_path, base_name)
                shot_directory = components['shot_dir']
                results.append(f"<shotdir> resolved to: /{base_name}/ (relative to {shot_directory})")

                # CREATE FOLDER STRUCTURE FIRST (before comp files)
                if create_folders:
                    folder_success, folder_message = self.create_shot_folder_structure(shot_directory, base_name)
                    if folder_success:
                        results.append(f"{folder_message}")
                    else:
                        results.append(f"Folder structure warning for {base_name}: {folder_message}")

                # Get frame range from primary clip (for render range)
                start_frame, end_frame = self.get_frame_range(primary_clip)

                # Get clip properties (resolution and fps) from primary clip
                width, height, fps = self.get_clip_properties(primary_clip)

                # Extract version info from primary clip
                current_version = self.parse_version_from_path(clip_path)

                # Get overwrite setting
                overwrite_existing = self.settings_manager.get_setting("overwrite_existing")

                # Log the detected properties
                duration = end_frame - start_frame + 1
                results.append(f"{base_name}: Primary layer frames {start_frame}-{end_frame} (duration: {duration})")
                results.append(f"Resolution: {width}x{height} @ {fps}fps")

                # Show VFX notes information for this shot
                if include_notes:
                    shot_notes = []
                    for clip_info_item in clip_group:
                        clip_notes = self.extract_vfx_notes(clip_info_item['clip'])
                        shot_notes.extend(clip_notes)

                    if shot_notes:
                        results.append(f"VFX Notes for {base_name}:")
                        for note in shot_notes:
                            preview = note['content'][:50] + "..." if len(note['content']) > 50 else note['content']
                            results.append(f"    - {note['source']}: {preview}")

                # REPORT DATA COLLECTION: Collect comprehensive clip data for each layer
                shot_data = {
                    'base_name': base_name,
                    'layers': [],
                    'generated_files': {},
                    'folder_structure_created': create_folders
                }

                for i, clip_info_item in enumerate(clip_group):
                    comprehensive_clip_data = self.collect_comprehensive_clip_data(clip_info_item, i)
                    shot_data['layers'].append(comprehensive_clip_data)

                # Generate Fusion comp file if enabled
                if generate_fusion:
                    fusion_path, fusion_filename, fusion_path_var, fusion_path_val, fusion_version = self.create_output_path(
                        clip_path, base_name, current_version, 'fusion', overwrite_existing
                    )

                    results.append(f"Fusion: v{current_version:03d} -> v{fusion_version:03d} {'(overwrite)' if overwrite_existing else '(next available)'}")
                    results.append(f"Fusion output: {fusion_path}")

                    # Create Fusion comp content
                    fusion_content = self.create_fusion_comp(
                        clip_group, str(fusion_path), exr_settings,
                        fusion_path.name, fusion_version, width, height, fps, base_name, fusion_path_var, fusion_path_val
                    )

                    # Write Fusion comp file atomically
                    success, message = write_file_atomically(fusion_path, fusion_content)
                    if success:
                        results.append(f"Fusion: {message}")
                        if include_notes and any(self.extract_vfx_notes(clip_info_item['clip']) for clip_info_item in clip_group):
                            results.append(f"Fusion: VFX notes added as StickyNotes")
                        
                        # Add to report data
                        shot_data['generated_files']['fusion'] = {
                            'path': str(fusion_path),
                            'filename': fusion_filename,
                            'version': fusion_version,
                            'path_variable': fusion_path_var,
                            'path_value': fusion_path_val,
                            'settings': exr_settings.copy()
                        }
                    else:
                        results.append(f"Fusion: {message}")

                # Generate Fusion Depth comp file if enabled
                if generate_fusion_depth:
                    depth_path, depth_filename, depth_path_var, depth_path_val, depth_version = self.create_output_path(
                        clip_path, base_name, current_version, 'fusion_depth', overwrite_existing
                    )

                    results.append(f"Depth: v{current_version:03d} -> v{depth_version:03d} {'(overwrite)' if overwrite_existing else '(next available)'}")
                    results.append(f"Depth output: {depth_path}")

                    # Create Fusion depth comp content
                    depth_content = self.create_fusion_depth_comp(
                        clip_group, exr_settings, base_name, depth_version,
                        width, height, fps, depth_path_var, depth_path_val
                    )

                    # Write Fusion depth comp file atomically
                    success, message = write_file_atomically(depth_path, depth_content)
                    if success:
                        results.append(f"Depth: {message}")
                        
                        # Add to report data
                        shot_data['generated_files']['fusion_depth'] = {
                            'path': str(depth_path),
                            'filename': depth_filename,
                            'version': depth_version,
                            'type': 'depth_extraction',
                            'settings': exr_settings.copy()
                        }
                    else:
                        results.append(f"Depth: {message}")

                # Generate Fusion Magic Mask comp file if enabled
                if generate_fusion_mmask:
                    mmask_path, mmask_filename, mmask_path_var, mmask_path_val, mmask_version = self.create_output_path(
                        clip_path, base_name, current_version, 'fusion_mmask', overwrite_existing
                    )

                    results.append(f"MMask: v{current_version:03d} -> v{mmask_version:03d} {'(overwrite)' if overwrite_existing else '(next available)'}")
                    results.append(f"MMask output: {mmask_path}")

                    # Create Fusion magic mask comp content
                    mmask_content = self.create_fusion_mmask_comp(
                        clip_group, exr_settings, base_name, mmask_version,
                        width, height, fps, mmask_path_var, mmask_path_val
                    )

                    # Write Fusion magic mask comp file atomically
                    success, message = write_file_atomically(mmask_path, mmask_content)
                    if success:
                        results.append(f"MMask: {message}")
                        
                        # Add to report data
                        shot_data['generated_files']['fusion_mmask'] = {
                            'path': str(mmask_path),
                            'filename': mmask_filename,
                            'version': mmask_version,
                            'type': 'magic_mask',
                            'settings': exr_settings.copy()
                        }
                    else:
                        results.append(f"MMask: {message}")

                # Generate Nuke script file if enabled
                if generate_nuke:
                    nuke_path, nuke_filename, nuke_path_var, nuke_path_val, nuke_version = self.create_output_path(
                        clip_path, base_name, current_version, 'nuke', overwrite_existing
                    )

                    # Get color management setting
                    color_management = self.settings_manager.get_setting("nuke_color_management")
                    if color_management == "aces_1.2":
                        color_info = "ACES 1.2"
                    elif color_management == "custom_ocio":
                        custom_config = self.settings_manager.get_setting("custom_ocio_config")
                        if custom_config:
                            config_name = Path(custom_config).stem
                            color_info = f"Custom OCIO ({config_name})"
                            # Validate OCIO file exists
                            if not Path(custom_config).exists():
                                results.append(f"Warning: OCIO config file not found: {custom_config}")
                            else:
                                results.append(f"OCIO config found: {custom_config}")
                                # Show OCIO settings being used (if debug enabled)
                                if debug_enabled:
                                    working_space = self.settings_manager.get_setting("custom_ocio_working_space")
                                    display = self.settings_manager.get_setting("custom_ocio_display")
                                    view = self.settings_manager.get_setting("custom_ocio_view")
                                    viewer_process = self.settings_manager.get_setting("custom_ocio_viewer_process")
                                    results.append(f"OCIO Settings: Working Space={working_space}, Display={display}, View={view}")
                                    results.append(f"Viewer Process: {viewer_process}")
                        else:
                            color_info = "Custom OCIO (Not Set)"
                    else:
                        color_info = "Nuke Default"

                    results.append(f"Nuke ({color_info}): v{current_version:03d} -> v{nuke_version:03d} {'(overwrite)' if overwrite_existing else '(next available)'}")
                    results.append(f"Nuke output: {nuke_path}")

                    # Create Nuke script content with color management
                    nuke_content = self.create_nuke_script(
                        clip_group, str(nuke_path), exr_settings,
                        nuke_path.name, nuke_version, width, height, fps, base_name, nuke_path_var, nuke_path_val, color_management
                    )

                    # Write Nuke script file atomically
                    success, message = write_file_atomically(nuke_path, nuke_content)
                    if success:
                        results.append(f"Nuke: {message}")
                        if include_notes and any(self.extract_vfx_notes(clip_info_item['clip']) for clip_info_item in clip_group):
                            results.append(f"Nuke: VFX notes added as StickyNotes")
                        
                        # Add to report data
                        shot_data['generated_files']['nuke'] = {
                            'path': str(nuke_path),
                            'filename': nuke_filename,
                            'version': nuke_version,
                            'path_variable': nuke_path_var,
                            'path_value': nuke_path_val,
                            'color_management': color_management,
                            'settings': exr_settings.copy()
                        }
                    else:
                        results.append(f"Nuke: {message}")

                # Show layer details and their individual frame ranges
                layer_details = []
                all_start_frames = []
                all_end_frames = []

                for clip_info_item in clip_group:
                    layer_num = clip_info_item['layer_num']
                    original_clip_name = clip_info_item['clip_name']
                    clip = clip_info_item['clip']
                    clip_path = clip.GetClipProperty("File Path")
                    current_version = self.parse_version_from_path(clip_path)

                    # Get individual frame range for this layer
                    layer_start_frame, layer_end_frame = self.get_frame_range(clip)
                    layer_duration = layer_end_frame - layer_start_frame + 1
                    all_start_frames.append(layer_start_frame)
                    all_end_frames.append(layer_end_frame)

                    # Show what loader path will be generated
                    if f"_L{layer_num:02d}_" in original_clip_name or f"_L{layer_num}_" in original_clip_name:
                        layer_name = f"L{layer_num:02d}"
                        display_layer = layer_name
                    else:
                        display_layer = "Main"

                    connection = " -> Output" if clip_info_item['layer_num'] == clip_group[0]['layer_num'] else ""
                    layer_details.append(f"    {display_layer}: frames {layer_start_frame}-{layer_end_frame} (duration: {layer_duration}){connection}")

                # Show overall comp range
                comp_start = min(all_start_frames)
                comp_end = max(all_end_frames)
                comp_duration = comp_end - comp_start + 1

                results.append(f"Layer frame ranges:")
                results.extend(layer_details)
                results.append(f"Overall comp range: {comp_start}-{comp_end} (duration: {comp_duration})")
                results.append(f"Render range: {start_frame}-{end_frame} (primary layer)")
                results.append("")  # Empty line between shots

                # Add shot data to report collection
                shot_groups_data[base_name] = shot_data

            except Exception as e:
                results.append(f"{base_name}: Error - {str(e)}")
                import traceback
                results.append(f"   Full error: {traceback.format_exc()}")

        # REPORT GENERATION: Create and write scene report (if enabled)
        generate_scene_report = self.settings_manager.get_setting("generate_scene_report")
        if generate_scene_report:
            try:
                report_data = self.create_scene_report(shot_groups_data, generation_results)
                if report_data:
                    report_success, report_message = self.write_scene_report(report_data)
                    if report_success:
                        results.append("Scene report generated successfully!")
                        results.append(f"Report location: {report_message.split(': ')[1]}")
                    else:
                        results.append(f"Scene report generation failed: {report_message}")
                else:
                    results.append("No data available for scene report generation")
            except Exception as e:
                results.append(f"Scene report error: {str(e)}")
        else:
            results.append("Scene report generation disabled in settings")

        return True, results

    def create_scene_report(self, shot_groups_data, generation_results):
        """Create comprehensive scene report with all clip data and generation results"""
        import datetime
        
        # Get scene information from the first clip
        if not shot_groups_data:
            return None
        
        # Extract scene info from first shot's first clip
        first_shot_data = list(shot_groups_data.values())[0]
        first_clip_data = first_shot_data['layers'][0] if first_shot_data['layers'] else None
        
        if not first_clip_data or not first_clip_data['file_info']['file_path']:
            return None
        
        # Extract path components
        first_clip_path = first_clip_data['file_info']['file_path']
        first_shot_name = first_shot_data['base_name']
        components = self.extract_path_components(first_clip_path, first_shot_name)
        
        # Try to detect Resolve version
        resolve_version = "Unknown"
        try:
            if self.resolve:
                # Try to get version info from Resolve
                resolve_version = "DaVinci Resolve (Connected)"
        except:
            pass
        
        # Build comprehensive report
        report = {
            "report_info": {
                "generated_at": datetime.datetime.now().isoformat(),
                "generator": "CompDeploy v1.0",
                "resolve_version": resolve_version,
                "total_shots": len(shot_groups_data),
                "total_clips": sum(len(shot_data['layers']) for shot_data in shot_groups_data.values())
            },
            "project_info": {
                "scene": components['scene_name'],
                "project": components['project_name'],
                "scene_directory": str(components['shot_dir'].parent)  # Scene directory path
            },
            "generation_settings": {
                "formats_generated": generation_results.get('formats_generated', []),
                "exr_settings": generation_results.get('exr_settings', {}),
                "vfx_notes_included": generation_results.get('vfx_notes_included', False),
                "overwrite_existing": generation_results.get('overwrite_existing', False),
                "color_management": generation_results.get('color_management', 'Unknown')
            },
            "shots": shot_groups_data,
            "summary": {
                "total_vfx_notes": sum(
                    sum(len(layer['vfx_notes']) for layer in shot_data['layers'])
                    for shot_data in shot_groups_data.values()
                ),
                "total_generated_files": sum(
                    len(shot_data.get('generated_files', {}))
                    for shot_data in shot_groups_data.values()
                ),
                "unique_resolutions": list(set(
                    f"{layer['technical_properties']['resolution']['width']}x{layer['technical_properties']['resolution']['height']}"
                    for shot_data in shot_groups_data.values()
                    for layer in shot_data['layers']
                )),
                "frame_rate_range": {
                    "fps_values": list(set(
                        layer['technical_properties']['fps']
                        for shot_data in shot_groups_data.values()
                        for layer in shot_data['layers']
                    )),
                    "frame_ranges": [
                        {
                            "shot": shot_name,
                            "start": min(layer['technical_properties']['frame_range']['start'] for layer in shot_data['layers']),
                            "end": max(layer['technical_properties']['frame_range']['end'] for layer in shot_data['layers'])
                        }
                        for shot_name, shot_data in shot_groups_data.items()
                    ]
                }
            }
        }
        
        return report

    def write_scene_report(self, report_data):
        """Write scene report JSON file to scene directory"""
        if not report_data:
            return False, "No report data to write"
        
        try:
            scene_name = report_data['project_info']['scene']
            scene_directory = report_data['project_info']['scene_directory']
            
            # Create report filename
            report_filename = f"{scene_name}_report.json"
            report_path = Path(scene_directory) / report_filename
            
            # Convert report to JSON with pretty formatting
            import json
            report_json = json.dumps(report_data, indent=2, ensure_ascii=False)
            
            # Write report using atomic writing
            success, message = write_file_atomically(report_path, report_json)
            
            if success:
                return True, f"Scene report written: {report_path}"
            else:
                return False, f"Failed to write scene report: {message}"
                
        except Exception as e:
            return False, f"Error creating scene report: {e}"

        return True, results


class ResolvePathTemplateDialog(QDialog):
    """Resolve styled dialog for editing path templates including render paths"""

    def __init__(self, parent, settings_manager):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Customize Output Paths")
        self.setModal(True)
        self.resize(1400, 700)  # Wider to accommodate render paths

        # Apply Resolve styling
        self.setStyleSheet(ResolveTheme.get_main_stylesheet())

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Customize Output Paths")
        title.setProperty("class", "title-label")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Main content in horizontal layout
        main_layout = QHBoxLayout()
        main_layout.setSpacing(20)

        # Left side - Template editing
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # SCRIPT PATHS SECTION
        script_title = QLabel("Script File Paths")
        script_title.setProperty("class", "section-title")
        script_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 12px; color: #4376A1;")
        left_layout.addWidget(script_title)

        # Fusion script template section
        fusion_script_label = QLabel("Fusion Studio Script Template")
        fusion_script_label.setProperty("class", "section-title")
        left_layout.addWidget(fusion_script_label)

        self.fusion_script_edit = QLineEdit()
        self.fusion_script_edit.setText(self.settings_manager.get_setting("fusion_output_path"))
        self.fusion_script_edit.setPlaceholderText("e.g., <shotdir>/comp/<shotname>_comp_v<version>.comp")
        left_layout.addWidget(self.fusion_script_edit)

        # Fusion script preview
        fusion_script_preview_label = QLabel("Script Preview:")
        fusion_script_preview_label.setStyleSheet("font-size: 12px; margin-top: 8px; margin-bottom: 4px;")
        left_layout.addWidget(fusion_script_preview_label)

        self.fusion_script_preview = QLabel()
        self.fusion_script_preview.setProperty("class", "path-label")
        self.fusion_script_preview.setWordWrap(True)
        left_layout.addWidget(self.fusion_script_preview)

        # Nuke script template section
        nuke_script_label = QLabel("Nuke Script Template")
        nuke_script_label.setProperty("class", "section-title")
        nuke_script_label.setStyleSheet("margin-top: 16px;")
        left_layout.addWidget(nuke_script_label)

        self.nuke_script_edit = QLineEdit()
        self.nuke_script_edit.setText(self.settings_manager.get_setting("nuke_output_path"))
        self.nuke_script_edit.setPlaceholderText("e.g., <shotdir>/comp/<shotname>_comp_v<version>.nk")
        left_layout.addWidget(self.nuke_script_edit)

        # Nuke script preview
        nuke_script_preview_label = QLabel("Script Preview:")
        nuke_script_preview_label.setStyleSheet("font-size: 12px; margin-top: 8px; margin-bottom: 4px;")
        left_layout.addWidget(nuke_script_preview_label)

        self.nuke_script_preview = QLabel()
        self.nuke_script_preview.setProperty("class", "path-label")
        self.nuke_script_preview.setWordWrap(True)
        left_layout.addWidget(self.nuke_script_preview)

        # RENDER PATHS SECTION
        render_title = QLabel("Render Output Paths")
        render_title.setProperty("class", "section-title")
        render_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 24px; margin-bottom: 12px; color: #F9423F;")
        left_layout.addWidget(render_title)

        # Fusion render template section
        fusion_render_label = QLabel("Fusion Render Output Template")
        fusion_render_label.setProperty("class", "section-title")
        left_layout.addWidget(fusion_render_label)

        self.fusion_render_edit = QLineEdit()
        self.fusion_render_edit.setText(self.settings_manager.get_setting("fusion_render_path"))
        self.fusion_render_edit.setPlaceholderText("e.g., <shotdir>/<render_folder>/<sequence_folder>/<render_filename>_<frame_format>.exr")
        left_layout.addWidget(self.fusion_render_edit)

        # Fusion render preview
        fusion_render_preview_label = QLabel("Render Preview:")
        fusion_render_preview_label.setStyleSheet("font-size: 12px; margin-top: 8px; margin-bottom: 4px;")
        left_layout.addWidget(fusion_render_preview_label)

        self.fusion_render_preview = QLabel()
        self.fusion_render_preview.setProperty("class", "path-label")
        self.fusion_render_preview.setWordWrap(True)
        left_layout.addWidget(self.fusion_render_preview)

        # Nuke render template section
        nuke_render_label = QLabel("Nuke Render Output Template")
        nuke_render_label.setProperty("class", "section-title")
        nuke_render_label.setStyleSheet("margin-top: 16px;")
        left_layout.addWidget(nuke_render_label)

        self.nuke_render_edit = QLineEdit()
        self.nuke_render_edit.setText(self.settings_manager.get_setting("nuke_render_path"))
        self.nuke_render_edit.setPlaceholderText("e.g., <shotdir>/<render_folder>/<sequence_folder>/<render_filename>_<frame_format>.exr")
        left_layout.addWidget(self.nuke_render_edit)

        # Nuke render preview
        nuke_render_preview_label = QLabel("Render Preview:")
        nuke_render_preview_label.setStyleSheet("font-size: 12px; margin-top: 8px; margin-bottom: 4px;")
        left_layout.addWidget(nuke_render_preview_label)

        self.nuke_render_preview = QLabel()
        self.nuke_render_preview.setProperty("class", "path-label")
        self.nuke_render_preview.setWordWrap(True)
        left_layout.addWidget(self.nuke_render_preview)

        # Preset buttons
        presets_label = QLabel("Quick Presets:")
        presets_label.setProperty("class", "section-title")
        presets_label.setStyleSheet("margin-top: 16px; margin-bottom: 8px;")
        left_layout.addWidget(presets_label)

        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(8)

        default_btn = QPushButton("Default")
        default_btn.setProperty("class", "small-button")
        default_btn.clicked.connect(self.set_default_presets)
        presets_layout.addWidget(default_btn)

        comp_work_btn = QPushButton("comp_work")
        comp_work_btn.setProperty("class", "small-button")
        comp_work_btn.clicked.connect(self.set_comp_work_presets)
        presets_layout.addWidget(comp_work_btn)

        render_subfolders_btn = QPushButton("render_subfolders")
        render_subfolders_btn.setProperty("class", "small-button")
        render_subfolders_btn.clicked.connect(self.set_render_subfolders_presets)
        presets_layout.addWidget(render_subfolders_btn)

        presets_layout.addStretch()
        left_layout.addLayout(presets_layout)
        left_layout.addStretch()

        main_layout.addWidget(left_panel, 1)

        # Right side - Available tokens
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        tokens_title = QLabel("Available Tokens")
        tokens_title.setProperty("class", "section-title")
        right_layout.addWidget(tokens_title)

        help_text = QLabel("Double-click any token to insert it into the active template:")
        help_text.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        right_layout.addWidget(help_text)

        # Create tokens table with categories
        tokens_table = QTableWidget()
        tokens = self.settings_manager.get_available_tokens()
        tokens_table.setRowCount(len(tokens))
        tokens_table.setColumnCount(3)
        tokens_table.setHorizontalHeaderLabels(["Token", "Description", "Type"])

        # Add explicit styling to fix white background issue on Windows
        tokens_table.setStyleSheet("""
            QTableWidget {
                background: #1a1a1a;
                alternate-background-color: #1f1f1f;
            }
            QTableWidget::item {
                background-color: #1a1a1a;
                color: #cccccc;
                padding: 6px;
                border: none;
            }
            QTableWidget::item:alternate {
                background-color: #1f1f1f;
            }
            QTableWidget::item:selected {
                background-color: #4376A1;
                color: #ffffff;
            }
            QTableWidget::item:hover {
                background-color: #333333;
            }
        """)

        row = 0
        for token, description in tokens.items():
            # Determine background color for alternating rows
            bg_color = QColor("#1a1a1a") if row % 2 == 0 else QColor("#1f1f1f")
            
            token_item = QTableWidgetItem(token)
            token_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            token_item.setBackground(bg_color)  # Force background
            token_item.setForeground(QColor("#cccccc"))  # Force text color
            
            desc_item = QTableWidgetItem(description)
            desc_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            desc_item.setBackground(bg_color)  # Force background
            desc_item.setForeground(QColor("#cccccc"))  # Force text color
            
            # Categorize tokens
            if token in ["<render_folder>", "<sequence_folder>", "<render_filename>", "<frame_format>"]:
                type_item = QTableWidgetItem("Render")
                type_item.setForeground(QColor("#F9423F"))  # Red for render tokens
            else:
                type_item = QTableWidgetItem("Script")
                type_item.setForeground(QColor("#4376A1"))  # Blue for script tokens
            type_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            type_item.setBackground(bg_color)  # Force background

            tokens_table.setItem(row, 0, token_item)
            tokens_table.setItem(row, 1, desc_item)
            tokens_table.setItem(row, 2, type_item)
            row += 1

        tokens_table.resizeColumnsToContents()
        tokens_table.horizontalHeader().setStretchLastSection(False)
        tokens_table.setColumnWidth(2, 60)  # Fixed width for type column
        tokens_table.horizontalHeader().setStretchLastSection(True)
        tokens_table.setAlternatingRowColors(True)
        tokens_table.itemDoubleClicked.connect(self.insert_token)

        right_layout.addWidget(tokens_table)

        main_layout.addWidget(right_panel, 1)
        layout.addLayout(main_layout)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Apply Changes")
        ok_btn.setProperty("class", "primary-button")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

        # Connect text change to preview update
        self.fusion_script_edit.textChanged.connect(self.update_preview)
        self.nuke_script_edit.textChanged.connect(self.update_preview)
        self.fusion_render_edit.textChanged.connect(self.update_preview)
        self.nuke_render_edit.textChanged.connect(self.update_preview)
        self.update_preview()

    def insert_token(self, item):
        """Insert selected token into the focused path edit"""
        if item.column() == 0:
            token = item.text()

            # Determine which field has focus
            if self.fusion_script_edit.hasFocus():
                target_edit = self.fusion_script_edit
            elif self.nuke_script_edit.hasFocus():
                target_edit = self.nuke_script_edit
            elif self.fusion_render_edit.hasFocus():
                target_edit = self.fusion_render_edit
            elif self.nuke_render_edit.hasFocus():
                target_edit = self.nuke_render_edit
            else:
                # Default to fusion script if no focus
                target_edit = self.fusion_script_edit

            cursor_pos = target_edit.cursorPosition()
            current_text = target_edit.text()
            new_text = current_text[:cursor_pos] + token + current_text[cursor_pos:]
            target_edit.setText(new_text)
            target_edit.setCursorPosition(cursor_pos + len(token))
            target_edit.setFocus()

    def set_default_presets(self):
        """Set default path templates with comp files in work subfolder - simplified render paths"""
        self.fusion_script_edit.setText("<shotdir>/comp/work/fusion/<shotname>_comp_v<version>.comp")
        self.nuke_script_edit.setText("<shotdir>/comp/work/nuke/<shotname>_comp_v<version>.nk")
        self.fusion_render_edit.setText("<shotdir>comp/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_0000.exr")
        self.nuke_render_edit.setText("<shotdir>/comp/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_%04d.exr")

    def set_comp_work_presets(self):
        """Set comp_work path templates - simplified render paths"""
        self.fusion_script_edit.setText("<shotdir>/comp_work/fusion/<shotname>_comp_v<version>.comp")
        self.nuke_script_edit.setText("<shotdir>/comp_work/nuke/<shotname>_comp_v<version>.nk")
        self.fusion_render_edit.setText("<shotdir>comp_work/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_0000.exr")
        self.nuke_render_edit.setText("<shotdir>/comp_work/render/<shotname>_comp_v<version>/<shotname>_comp_v<version>_%04d.exr")

    def set_render_subfolders_presets(self):
        """Set render with organized subfolders - simplified render paths"""
        self.fusion_script_edit.setText("<shotdir>comp/work/<shotname>_comp_v<version>.comp")
        self.nuke_script_edit.setText("<shotdir>/comp/work/<shotname>_comp_v<version>.nk")
        self.fusion_render_edit.setText("<shotdir>render/comp/<shotname>_comp_v<version>/<shotname>_comp_v<version>_0000.exr")
        self.nuke_render_edit.setText("<shotdir>/render/comp/<shotname>_comp_v<version>/<shotname>_comp_v<version>_%04d.exr")

    def update_preview(self):
        """Update the preview with example values - simplified for both script and render paths"""
        # Get all template texts
        fusion_script_template = self.fusion_script_edit.text()
        nuke_script_template = self.nuke_script_edit.text()
        fusion_render_template = self.fusion_render_edit.text()
        nuke_render_template = self.nuke_render_edit.text()

        # Use same token values for both script and render paths
        example_tokens = {
            "<shotdir>": "/bz_av_sh0010",
            "<shotname>": "bz_av_sh0010",
            "<version>": "001",
            "<current_version>": "000",
            "<v###>": "v001",
            "<cv###>": "v000",
            "<filename>": "bz_av_sh0010_comp_v001",
            "<ext>": ".comp/.nk"
        }

        # Replace tokens using standard method for all paths
        fusion_script_preview = self.settings_manager.replace_tokens(fusion_script_template, example_tokens)
        nuke_script_preview = self.settings_manager.replace_tokens(nuke_script_template, example_tokens)
        fusion_render_preview = self.settings_manager.replace_tokens(fusion_render_template, example_tokens)
        nuke_render_preview = self.settings_manager.replace_tokens(nuke_render_template, example_tokens)

        # Update all preview labels
        self.fusion_script_preview.setText(fusion_script_preview)
        self.nuke_script_preview.setText(nuke_script_preview)
        self.fusion_render_preview.setText(fusion_render_preview)
        self.nuke_render_preview.setText(nuke_render_preview)

    def get_fusion_script_template(self):
        """Get the edited Fusion script path template"""
        return self.fusion_script_edit.text()

    def get_nuke_script_template(self):
        """Get the edited Nuke script path template"""
        return self.nuke_script_edit.text()

    def get_fusion_render_template(self):
        """Get the edited Fusion render path template"""
        return self.fusion_render_edit.text()

    def get_nuke_render_template(self):
        """Get the edited Nuke render path template"""
        return self.nuke_render_edit.text()

class FolderStructureTab(QWidget):
    """Complete folder structure management tab"""
    
    def __init__(self, settings_manager):
        super().__init__()
        self.settings_manager = settings_manager
        self.folder_manager = settings_manager.folder_manager
        self.external_template_path = ""
        self.init_ui()
        self.load_template()

        self.enable_folders_check.toggled.connect(self.on_enable_toggled)

    def on_enable_toggled(self, checked):
        """Immediately save the enabled state when checkbox is toggled"""
        # Save to settings only (not template)
        self.settings_manager.set_setting("create_folder_structure", checked)
        self.settings_manager.save_settings()
        
        self.update_preview()
        
        # Sync with main tab checkbox using stored reference
        if hasattr(self, 'main_window') and hasattr(self.main_window, 'create_folders_check'):
            self.main_window.create_folders_check.blockSignals(True)
            self.main_window.create_folders_check.setChecked(checked)
            self.main_window.create_folders_check.blockSignals(False)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header section
        header_layout = QHBoxLayout()
        
        title = QLabel("Shot Folder Structure")
        title.setProperty("class", "title-label")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Enable/Disable toggle
        self.enable_folders_check = QCheckBox("Enable folder creation")
        self.enable_folders_check.setChecked(True)
        self.enable_folders_check.setToolTip("Enable automatic folder structure creation")
        self.enable_folders_check.toggled.connect(self.on_enable_changed)
        header_layout.addWidget(self.enable_folders_check)
        
        layout.addLayout(header_layout)
        
        # Main content in horizontal layout
        main_layout = QHBoxLayout()
        main_layout.setSpacing(20)
        
        # Left panel - Folder structure editor
        left_panel = self.create_editor_panel()
        main_layout.addWidget(left_panel, 1.5)
        
        # Right panel - Preview and controls
        right_panel = self.create_preview_panel()
        main_layout.addWidget(right_panel, 1)
        
        layout.addLayout(main_layout)
        
        # Bottom controls
        controls_layout = QHBoxLayout()

        # Preset buttons (right side)
        preset_label = QLabel("Presets:")
        preset_label.setStyleSheet("color: #cccccc; font-size: 12px; margin-right: 8px;")
        controls_layout.addWidget(preset_label)

        sample_btn = QPushButton("Create Sample Template")
        sample_btn.setProperty("class", "small-button")
        sample_btn.setToolTip("Create a sample JSON template file to use as starting point")
        sample_btn.clicked.connect(self.create_sample_template)
        controls_layout.addWidget(sample_btn)

        vfx_preset_btn = QPushButton("VFX")
        vfx_preset_btn.setProperty("class", "small-button")
        vfx_preset_btn.setToolTip("Standard VFX folder structure")
        vfx_preset_btn.clicked.connect(self.apply_vfx_preset)
        controls_layout.addWidget(vfx_preset_btn)

        minimal_preset_btn = QPushButton("Minimal")
        minimal_preset_btn.setProperty("class", "small-button")
        minimal_preset_btn.setToolTip("Minimal folder structure")
        minimal_preset_btn.clicked.connect(self.apply_minimal_preset)
        controls_layout.addWidget(minimal_preset_btn)

        controls_layout.addStretch()

        # Action buttons (far right)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_to_default)
        controls_layout.addWidget(reset_btn)

        save_btn = QPushButton("Save")
        save_btn.setProperty("class", "primary-button")
        save_btn.clicked.connect(self.save_template)
        controls_layout.addWidget(save_btn)

        layout.addLayout(controls_layout)
            
    def create_editor_panel(self):
        """Create the left editor panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Template description
        desc_layout = QHBoxLayout()
        desc_label = QLabel("Description:")
        desc_label.setStyleSheet("color: #cccccc; font-size: 13px; min-width: 80px;")
        desc_layout.addWidget(desc_label)
        
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Enter template description...")
        self.description_edit.textChanged.connect(self.on_template_changed)
        desc_layout.addWidget(self.description_edit)
        
        layout.addLayout(desc_layout)
        
        # Folder structure editor
        editor_label = QLabel("Folder Structure:")
        editor_label.setProperty("class", "section-title")
        editor_label.setStyleSheet("margin-top: 12px; margin-bottom: 8px;")
        layout.addWidget(editor_label)
        
        # Tree widget for folder structure
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(["Folder Name", "Description"])
        self.folder_tree.setAlternatingRowColors(True)
        self.folder_tree.setRootIsDecorated(True)
        self.folder_tree.setDragDropMode(QTreeWidget.InternalMove)
        self.folder_tree.itemChanged.connect(self.on_item_changed)
        self.folder_tree.itemSelectionChanged.connect(self.on_selection_changed)

        # Force dark backgrounds for tree items (Windows fix)
        self.folder_tree.setStyleSheet("""
            QTreeWidget {
                background: #1a1a1a;
                alternate-background-color: #1f1f1f;
            }
            QTreeWidget::item {
                background-color: #1a1a1a;
                color: #cccccc;
                padding: 4px;
                border: none;
            }
            QTreeWidget::item:alternate {
                background-color: #1f1f1f;
            }
            QTreeWidget::item:selected {
                background-color: #4376A1;
                color: #ffffff;
            }
            QTreeWidget::item:hover {
                background-color: #333333;
            }
        """)
        
        # Context menu
        self.folder_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.folder_tree)
        
        # Editor controls
        controls_layout = QHBoxLayout()
        
        self.add_main_btn = QPushButton("Add Main Folder")
        self.add_main_btn.setProperty("class", "small-button")
        self.add_main_btn.clicked.connect(self.add_main_folder)
        controls_layout.addWidget(self.add_main_btn)
        
        self.add_sub_btn = QPushButton("Add Subfolder")
        self.add_sub_btn.setProperty("class", "small-button")
        self.add_sub_btn.setEnabled(False)
        self.add_sub_btn.clicked.connect(self.add_subfolder)
        controls_layout.addWidget(self.add_sub_btn)
        
        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setProperty("class", "small-button")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self.remove_selected)
        controls_layout.addWidget(self.remove_btn)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        return panel
    
    def create_preview_panel(self):
        """Create the right preview panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        
        preview_label = QLabel("Preview")
        preview_label.setProperty("class", "section-title")
        layout.addWidget(preview_label)
        
        preview_desc = QLabel("Folders that will be created:")
        preview_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(preview_desc)
        
        # Preview tree (read-only)
        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderLabel("Folder Structure")
        self.preview_tree.setAlternatingRowColors(True)
        self.preview_tree.setRootIsDecorated(True)
        self.preview_tree.setStyleSheet("QTreeWidget { background: #1a1a1a; }")
        layout.addWidget(self.preview_tree)
        
        # Statistics
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 8px;")
        layout.addWidget(self.stats_label)
        
        # Template file management section
        template_info_group = QGroupBox("Template Files")
        template_info_layout = QVBoxLayout(template_info_group)
        
        # Current internal template
        internal_label = QLabel("Internal Template:")
        internal_label.setStyleSheet("color: #cccccc; font-size: 12px; font-weight: bold; margin-bottom: 4px;")
        template_info_layout.addWidget(internal_label)
        
        self.template_path_label = QLabel()
        self.template_path_label.setProperty("class", "path-label")
        self.template_path_label.setWordWrap(True)
        template_info_layout.addWidget(self.template_path_label)
        
        # Internal template controls
        internal_controls_layout = QHBoxLayout()
        
        open_internal_btn = QPushButton("Edit Internal")
        open_internal_btn.setProperty("class", "small-button")
        open_internal_btn.setToolTip("Open internal JSON template in external editor")
        open_internal_btn.clicked.connect(self.open_template_file)
        internal_controls_layout.addWidget(open_internal_btn)
        
        save_as_btn = QPushButton("Export...")
        save_as_btn.setProperty("class", "small-button")
        save_as_btn.setToolTip("Export current structure to external JSON file")
        save_as_btn.clicked.connect(self.export_template)
        internal_controls_layout.addWidget(save_as_btn)
        
        internal_controls_layout.addStretch()
        template_info_layout.addLayout(internal_controls_layout)
        
        # External template section
        external_label = QLabel("External Template:")
        external_label.setStyleSheet("color: #cccccc; font-size: 12px; font-weight: bold; margin-top: 12px; margin-bottom: 4px;")
        template_info_layout.addWidget(external_label)
        
        # External template path display
        self.external_template_label = QLabel("None selected")
        self.external_template_label.setProperty("class", "path-label")
        self.external_template_label.setWordWrap(True)
        template_info_layout.addWidget(self.external_template_label)
        
        # External template controls
        external_controls_layout = QHBoxLayout()
        
        browse_btn = QPushButton("Browse...")
        browse_btn.setProperty("class", "small-button")
        browse_btn.setToolTip("Select external JSON template file")
        browse_btn.clicked.connect(self.browse_external_template)
        external_controls_layout.addWidget(browse_btn)
        
        load_btn = QPushButton("Load External")
        load_btn.setProperty("class", "primary-button")
        load_btn.setToolTip("Load structure from external JSON file")
        load_btn.clicked.connect(self.load_external_template)
        external_controls_layout.addWidget(load_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.setProperty("class", "small-button")  
        clear_btn.setToolTip("Clear external template selection")
        clear_btn.clicked.connect(self.clear_external_template)
        external_controls_layout.addWidget(clear_btn)
        
        external_controls_layout.addStretch()
        template_info_layout.addLayout(external_controls_layout)
        
        layout.addWidget(template_info_group)
        
        return panel
    
    def browse_external_template(self):
        """Browse for external JSON template file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Folder Structure Template",
            self.external_template_path or "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.external_template_path = file_path
            self.external_template_label.setText(file_path)

    def clear_external_template(self):
        """Clear external template selection"""
        self.external_template_path = ""
        self.external_template_label.setText("None selected")

    def load_external_template(self):
        """Load folder structure from external JSON file"""
        if not self.external_template_path:
            QMessageBox.warning(self, "No Template Selected", "Please select an external template file first.")
            return
        
        try:
            # Validate file exists
            if not os.path.exists(self.external_template_path):
                QMessageBox.warning(self, "File Not Found", f"Template file not found:\n{self.external_template_path}")
                return
            
            # Load and parse JSON
            with open(self.external_template_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            
            # Validate template structure
            if not self.validate_external_template(template_data):
                return
            
            # Confirm replacement
            reply = QMessageBox.question(
                self, "Load External Template", 
                f"Load template from:\n{self.external_template_path}\n\n"
                "This will replace the current folder structure. Continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # Load template into editor
            self.load_template_from_data(template_data)
            
            QMessageBox.information(
                self, "Template Loaded", 
                f"Successfully loaded template:\n{os.path.basename(self.external_template_path)}\n\n"
                "Don't forget to click 'Save Changes' to make it permanent!"
            )
            
        except json.JSONDecodeError as e:
            QMessageBox.warning(
                self, "Invalid JSON", 
                f"Error parsing JSON file:\n{str(e)}\n\n"
                "Please check that the file contains valid JSON."
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Error Loading Template", 
                f"Error loading template file:\n{str(e)}"
            )

    def validate_external_template(self, template_data):
        """Validate external template structure - RECURSIVE VERSION"""
        try:
            # Check if it's a dictionary
            if not isinstance(template_data, dict):
                QMessageBox.warning(
                    self, "Invalid Template", 
                    "Template must be a JSON object (dictionary)."
                )
                return False
            
            # Check for required folder_structure key
            if 'folder_structure' not in template_data:
                QMessageBox.warning(
                    self, "Invalid Template", 
                    "Template must contain a 'folder_structure' section.\n\n"
                    "Expected format:\n"
                    "{\n"
                    '  "enabled": true,\n'
                    '  "description": "Template description",\n'
                    '  "folder_structure": { ... }\n'
                    "}"
                )
                return False
            
            # Check folder_structure is a dictionary
            folder_structure = template_data['folder_structure']
            if not isinstance(folder_structure, dict):
                QMessageBox.warning(
                    self, "Invalid Template", 
                    "The 'folder_structure' must be an object containing folders."
                )
                return False
            
            # Recursive validation function
            def validate_folder_dict(folder_dict, path="root", depth=0):
                """Recursively validate folder structure"""
                # Prevent excessive nesting
                if depth > 10:
                    QMessageBox.warning(
                        self, "Invalid Template",
                        f"Folder nesting too deep at '{path}' (max 10 levels allowed)"
                    )
                    return False
                
                for folder_name, folder_config in folder_dict.items():
                    current_path = f"{path}/{folder_name}"
                    
                    # Each folder must have a dict config
                    if not isinstance(folder_config, dict):
                        QMessageBox.warning(
                            self, "Invalid Template", 
                            f"Folder '{current_path}' configuration must be an object.\n\n"
                            "Expected format:\n"
                            f'"{folder_name}": {{\n'
                            '  "description": "Folder description",\n'
                            '  "subfolders": { ... }\n'
                            "}"
                        )
                        return False
                    
                    # Check subfolders if present
                    if 'subfolders' in folder_config:
                        subfolders = folder_config['subfolders']
                        
                        # Subfolders must be a dict (new recursive structure)
                        if not isinstance(subfolders, dict):
                            QMessageBox.warning(
                                self, "Invalid Template", 
                                f"Subfolders for '{current_path}' must be an object (dict).\n\n"
                                "New format requires nested structure:\n"
                                '"subfolders": {\n'
                                '  "subfolder_name": {\n'
                                '    "description": "...",\n'
                                '    "subfolders": { ... }\n'
                                '  }\n'
                                "}"
                            )
                            return False
                        
                        # Recursively validate subfolders
                        if subfolders:  # Only validate if non-empty
                            if not validate_folder_dict(subfolders, current_path, depth + 1):
                                return False
                
                return True
            
            # Validate the entire structure recursively
            return validate_folder_dict(folder_structure)
            
        except Exception as e:
            QMessageBox.warning(
                self, "Validation Error", 
                f"Error validating template:\n{str(e)}"
            )
            return False

    def load_template_from_data(self, template_data):
        """Load template data into the editor - RECURSIVE VERSION"""
        try:
            
            # Load description
            self.description_edit.setText(template_data.get('description', ''))
            
            # Clear and populate tree
            self.folder_tree.clear()
            
            folder_structure = template_data.get('folder_structure', {})
            
            def add_tree_items_recursive(folder_dict, parent_item=None):
                """Recursively add folders to tree widget"""
                for folder_name, config in folder_dict.items():
                    # Get description (handle both old string format and new dict format)
                    if isinstance(config, dict):
                        description = config.get('description', '')
                        subfolders = config.get('subfolders', {})
                    else:
                        # Backwards compatibility: old format had strings as subfolder values
                        description = str(config)
                        subfolders = {}
                    
                    # Create tree item
                    item = QTreeWidgetItem([folder_name, description])
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                    item.setExpanded(True)
                    
                    # Add to parent or top level
                    if parent_item is None:
                        self.folder_tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    
                    # Recursively add subfolders
                    if subfolders and isinstance(subfolders, dict):
                        add_tree_items_recursive(subfolders, item)
            
            # Start recursive population
            add_tree_items_recursive(folder_structure)
            
            # Update preview
            self.update_preview()
            
        except Exception as e:
            QMessageBox.warning(
                self, "Error Loading Template", 
                f"Error loading template data:\n{str(e)}"
            )

    def export_template(self):
        """Export current folder structure to external JSON file - RECURSIVE VERSION"""
        try:
            # Get save path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Folder Structure Template",
                f"folder_structure_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if not file_path:
                return
            
            # Build template (NO enabled field)
            template = {
                'description': self.description_edit.text().strip() or "Exported folder structure template",
                'folder_structure': {},
                'exported_from': "CompDeploy v1.0",
                'exported_at': datetime.datetime.now().isoformat()
            }
            
            def extract_tree_recursive(parent_item, parent_dict):
                """Recursively extract folder structure from tree widget"""
                child_count = parent_item.childCount() if parent_item else self.folder_tree.topLevelItemCount()
                
                for i in range(child_count):
                    if parent_item:
                        item = parent_item.child(i)
                    else:
                        item = self.folder_tree.topLevelItem(i)
                    
                    folder_name = item.text(0).strip()
                    folder_desc = item.text(1).strip()
                    
                    if not folder_name:
                        continue
                    
                    # Create folder config with description and subfolders
                    folder_config = {
                        'description': folder_desc,
                        'subfolders': {}
                    }
                    
                    # Recursively extract subfolders
                    if item.childCount() > 0:
                        extract_tree_recursive(item, folder_config['subfolders'])
                    
                    # Add to parent dictionary
                    parent_dict[folder_name] = folder_config
            
            # Extract from tree starting at root
            extract_tree_recursive(None, template['folder_structure'])
            
            # Write template to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(template, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(
                self, "Template Exported", 
                f"Template exported successfully:\n{file_path}"
            )
            
        except Exception as e:
            QMessageBox.warning(
                self, "Export Error", 
                f"Error exporting template:\n{str(e)}"
            )

    
    def show_context_menu(self, position):
        """Show context menu for tree items - RECURSIVE VERSION"""
        item = self.folder_tree.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #2a2a2a;
                color: #cccccc;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
            QMenu::item {
                padding: 6px 12px;
                border: none;
            }
            QMenu::item:selected {
                background: #4376A1;
                color: #ffffff;
            }
        """)
        
        # ANY item can now have subfolders added (not just main folders)
        add_sub_action = menu.addAction("Add Subfolder")
        add_sub_action.triggered.connect(lambda: self.add_subfolder_to_item(item))
        
        menu.addSeparator()
        
        # Determine item type for labeling
        item_type = "Folder" if item.parent() is None else "Subfolder"
        
        edit_action = menu.addAction(f"Edit {item_type}")
        edit_action.triggered.connect(lambda: self.edit_item(item))
        
        remove_action = menu.addAction(f"Remove {item_type}")
        remove_action.triggered.connect(lambda: self.remove_item(item))
        
        menu.exec_(self.folder_tree.mapToGlobal(position))
    
    def on_enable_changed(self):
        """Handle enable/disable toggle"""
        enabled = self.enable_folders_check.isChecked()
        
        # Enable/disable editor controls
        self.folder_tree.setEnabled(enabled)
        self.add_main_btn.setEnabled(enabled)
        self.add_sub_btn.setEnabled(enabled and self.folder_tree.currentItem() is not None)
        self.remove_btn.setEnabled(enabled and self.folder_tree.currentItem() is not None)
        
        self.update_preview()
    
    def on_selection_changed(self):
        """Handle selection changes in the tree - RECURSIVE VERSION"""
        current_item = self.folder_tree.currentItem()
        has_selection = current_item is not None
        enabled = self.enable_folders_check.isChecked()
        
        # Update button states
        # Now ANY selected item can have subfolders added (not just main folders)
        self.add_sub_btn.setEnabled(enabled and has_selection)
        self.remove_btn.setEnabled(enabled and has_selection)
    
    def on_item_changed(self, item, column):
        """Handle item text changes"""
        self.on_template_changed()
    
    def on_template_changed(self):
        """Handle any template changes"""
        self.update_preview()
    
    def add_main_folder(self):
        """Add a new main folder"""
        dialog = FolderEditDialog(self, "Add Main Folder")
        if dialog.exec() == QDialog.Accepted:
            name, description = dialog.get_values()
            
            # Check for duplicates
            for i in range(self.folder_tree.topLevelItemCount()):
                if self.folder_tree.topLevelItem(i).text(0) == name:
                    QMessageBox.warning(self, "Duplicate Name", f"Folder '{name}' already exists!")
                    return
            
            item = QTreeWidgetItem([name, description])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.folder_tree.addTopLevelItem(item)
            self.folder_tree.setCurrentItem(item)
            self.on_template_changed()
    
    def add_subfolder(self):
        """Add subfolder to selected item - works at ANY level now"""
        current_item = self.folder_tree.currentItem()
        if current_item:
            self.add_subfolder_to_item(current_item)
    
    def add_subfolder_to_item(self, parent_item):
        """Add subfolder to specific parent item"""
        dialog = FolderEditDialog(self, "Add Subfolder")
        if dialog.exec() == QDialog.Accepted:
            name, description = dialog.get_values()
            
            # Check for duplicates within this parent
            for i in range(parent_item.childCount()):
                if parent_item.child(i).text(0) == name:
                    QMessageBox.warning(self, "Duplicate Name", f"Subfolder '{name}' already exists in '{parent_item.text(0)}'!")
                    return
            
            item = QTreeWidgetItem([name, description])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            parent_item.addChild(item)
            parent_item.setExpanded(True)
            self.folder_tree.setCurrentItem(item)
            self.on_template_changed()
    
    def edit_item(self, item):
        """Edit selected item"""
        current_name = item.text(0)
        current_desc = item.text(1)
        
        folder_type = "Main Folder" if item.parent() is None else "Subfolder"
        dialog = FolderEditDialog(self, f"Edit {folder_type}", current_name, current_desc)
        
        if dialog.exec() == QDialog.Accepted:
            name, description = dialog.get_values()
            item.setText(0, name)
            item.setText(1, description)
            self.on_template_changed()
    
    def remove_selected(self):
        """Remove selected item"""
        current_item = self.folder_tree.currentItem()
        if current_item:
            self.remove_item(current_item)
    
    def remove_item(self, item):
        """Remove specific item"""
        folder_name = item.text(0)
        folder_type = "folder" if item.parent() is None else "subfolder"
        
        reply = QMessageBox.question(
            self, "Remove Folder", 
            f"Remove {folder_type} '{folder_name}'?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if item.parent():
                item.parent().removeChild(item)
            else:
                self.folder_tree.takeTopLevelItem(self.folder_tree.indexOfTopLevelItem(item))
            self.on_template_changed()
    
    def load_template(self):
        """Load current template into the editor"""
        try:
            template = self.folder_manager.load_folder_template()
            self.load_template_from_data(template)
            
            # Load enabled state from SETTINGS, not template
            enabled = self.settings_manager.get_setting("create_folder_structure")
            self.enable_folders_check.setChecked(enabled)
            
            # Update template path
            template_path = self.folder_manager.get_template_file_path()
            self.template_path_label.setText(str(template_path))
            
            if not self.external_template_path:
                self.external_template_label.setText("None selected")
            
        except Exception as e:
            QMessageBox.warning(self, "Error Loading Template", f"Could not load folder template:\n{e}")
        
    def save_template(self):
        """Save current editor state to template - RECURSIVE VERSION"""
        try:
            # Build template from current editor state (NO enabled field)
            template = {
                'description': self.description_edit.text().strip() or "Custom folder structure template",
                'folder_structure': {}
            }
            
            def extract_tree_recursive(parent_item, parent_dict):
                """Recursively extract folder structure from tree widget"""
                child_count = parent_item.childCount() if parent_item else self.folder_tree.topLevelItemCount()
                
                for i in range(child_count):
                    if parent_item:
                        item = parent_item.child(i)
                    else:
                        item = self.folder_tree.topLevelItem(i)
                    
                    folder_name = item.text(0).strip()
                    folder_desc = item.text(1).strip()
                    
                    if not folder_name:
                        continue
                    
                    folder_config = {
                        'description': folder_desc,
                        'subfolders': {}
                    }
                    
                    if item.childCount() > 0:
                        extract_tree_recursive(item, folder_config['subfolders'])
                    
                    parent_dict[folder_name] = folder_config
            
            extract_tree_recursive(None, template['folder_structure'])
            
            # Save template (structure only, no enabled state)
            success = self.folder_manager.save_folder_template(template)
            
            if success:
                QMessageBox.information(self, "Template Saved", "Folder structure template saved successfully!")
            else:
                QMessageBox.warning(self, "Save Error", "Failed to save folder structure template.")
        
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving template:\n{e}")

    def update_preview(self):
        """Update the preview tree - RECURSIVE VERSION"""
        self.preview_tree.clear()
        
        if not self.enable_folders_check.isChecked():
            disabled_item = QTreeWidgetItem(["📁 Folder structure creation disabled"])
            disabled_item.setForeground(0, QColor("#666"))
            self.preview_tree.addTopLevelItem(disabled_item)
            self.stats_label.setText("Folder structure creation is disabled")
            return
        
        # Add example shot root
        root_item = QTreeWidgetItem([f"📁 example_shot_sh0010/ (Shot Directory)"])
        root_item.setExpanded(True)
        self.preview_tree.addTopLevelItem(root_item)
        
        folder_count = 0
        main_folder_count = 0
        
        def add_preview_recursive(parent_tree_item, parent_editor_item, is_root=False):
            """Recursively add preview items from editor tree"""
            nonlocal folder_count, main_folder_count
            
            child_count = parent_editor_item.childCount() if parent_editor_item else self.folder_tree.topLevelItemCount()
            
            for i in range(child_count):
                if parent_editor_item:
                    editor_item = parent_editor_item.child(i)
                else:
                    editor_item = self.folder_tree.topLevelItem(i)
                
                folder_name = editor_item.text(0).strip()
                
                if not folder_name:
                    continue
                
                # Create preview item
                preview_item = QTreeWidgetItem([f"📁 {folder_name}/"])
                preview_item.setExpanded(True)
                parent_tree_item.addChild(preview_item)
                
                folder_count += 1
                if is_root:
                    main_folder_count += 1
                
                # Recursively add children
                if editor_item.childCount() > 0:
                    add_preview_recursive(preview_item, editor_item, False)
        
        # Start recursive preview from editor tree root
        add_preview_recursive(root_item, None, True)
        
        # Update stats
        self.stats_label.setText(f"{folder_count} total folders ({main_folder_count} main folders)")

    def create_sample_template(self):
        """Create a sample external template file"""
        sample_template = {
            "enabled": True,
            "description": "Sample VFX folder structure template",
            "folder_structure": {
                "comp": {
                    "description": "Compositing files and renders",
                    "subfolders": {
                        "work": "Working composition files",
                        "render": "Final renders",
                        "preview": "Preview renders and dailies"
                    }
                },
                "plate": {
                    "description": "Original plates and footage",
                    "subfolders": {
                        "original": "Untouched original footage",
                        "conform": "Conformed and processed plates"
                    }
                },
                "reference": {
                    "description": "Reference materials and assets",
                    "subfolders": {
                        "images": "Reference images and stills",
                        "video": "Reference video clips"
                    }
                }
            }
        }
        
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Create Sample Template",
                f"sample_folder_structure.json",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(sample_template, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(
                    self, "Sample Created", 
                    f"Sample template created:\n{file_path}\n\n"
                    "You can edit this file and load it back into CompDeploy."
                )
        
        except Exception as e:
            QMessageBox.warning(
                self, "Error Creating Sample", 
                f"Error creating sample template:\n{str(e)}"
            )
    
    def apply_vfx_preset(self):
        """Apply VFX standard preset"""
        reply = QMessageBox.question(
            self, "Apply VFX Preset", 
            "Replace current folder structure with VFX Standard preset?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.description_edit.setText("Standard VFX folder structure with comprehensive organization")
            
            # Clear and populate with VFX preset
            self.folder_tree.clear()
            
            vfx_structure = [
                ("comp", "Compositing files and renders", [
                    ("work", "Working composition files"),
                    ("render", "Final renders"),
                    ("preview", "Preview renders and dailies"),
                    ("elements", "Individual elements and passes")
                ]),
                ("plate", "Original plates and footage", [
                    ("original", "Untouched original footage"),
                    ("conform", "Conformed and processed plates"),
                    ("temp", "Temporary plate processing")
                ]),
                ("reference", "Reference materials and assets", [
                    ("images", "Reference images and stills"),
                    ("video", "Reference video clips"),
                    ("assets", "3D assets and models")
                ]),
                ("tracking", "Camera tracking and matchmove data", [
                    ("data", "Tracking data files"),
                    ("export", "Exported tracking information")
                ]),
                ("roto", "Rotoscoping and masking work", [
                    ("work", "Work-in-progress roto files"),
                    ("final", "Final approved roto shapes")
                ])
            ]
            
            self._populate_tree_from_structure(vfx_structure)
            self.on_template_changed()
    
    def apply_minimal_preset(self):
        """Apply minimal preset"""
        reply = QMessageBox.question(
            self, "Apply Minimal Preset", 
            "Replace current folder structure with Minimal preset?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.description_edit.setText("Minimal folder structure for simple projects")
            
            # Clear and populate with minimal preset
            self.folder_tree.clear()
            
            minimal_structure = [
                ("comp", "Compositing files and renders", [
                    ("work", "Working composition files"),
                    ("render", "Final renders")
                ]),
                ("reference", "Reference materials", [
                    ("images", "Reference images"),
                    ("video", "Reference video")
                ])
            ]
            
            self._populate_tree_from_structure(minimal_structure)
            self.on_template_changed()
    
    def _populate_tree_from_structure(self, structure):
        """Helper method to populate tree from structure data - RECURSIVE VERSION"""
        
        def add_items_recursive(items_list, parent_item=None):
            """Recursively add items from nested structure list"""
            for item_data in items_list:
                if len(item_data) == 3:
                    # Format: (name, description, subfolders_list)
                    folder_name, folder_desc, subfolders = item_data
                elif len(item_data) == 2:
                    # Format: (name, description) - no subfolders
                    folder_name, folder_desc = item_data
                    subfolders = []
                else:
                    continue
                
                # Create tree item
                tree_item = QTreeWidgetItem([folder_name, folder_desc])
                tree_item.setFlags(tree_item.flags() | Qt.ItemIsEditable)
                tree_item.setExpanded(True)
                
                # Add to parent or root
                if parent_item is None:
                    self.folder_tree.addTopLevelItem(tree_item)
                else:
                    parent_item.addChild(tree_item)
                
                # Recursively add subfolders
                if subfolders:
                    add_items_recursive(subfolders, tree_item)
        
        # Start recursive population from root
        add_items_recursive(structure)
    
    def reset_to_default(self):
        """Reset to default template"""
        reply = QMessageBox.question(
            self, "Reset Template", 
            "Reset folder structure template to default?\n\nThis will overwrite any custom changes.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success = self.folder_manager.save_folder_template(self.folder_manager.default_template)
            if success:
                self.load_template()
                QMessageBox.information(self, "Template Reset", "Template reset to default successfully!")
            else:
                QMessageBox.warning(self, "Reset Error", "Failed to reset template to default.")
    
    def open_template_file(self):
        """Open template JSON file in external editor"""
        try:
            import subprocess
            template_path = self.folder_manager.get_template_file_path()
            
            # Ensure file exists
            if not template_path.exists():
                template = self.folder_manager.load_folder_template()
                self.folder_manager.save_folder_template(template)
            
            # Platform-specific file opening
            system = platform.system()
            
            if system == "Windows":
                os.startfile(str(template_path))
            elif system == "Darwin":  # macOS
                subprocess.call(["open", str(template_path)])
            else:  # Linux
                subprocess.call(["xdg-open", str(template_path)])
            
            QMessageBox.information(
                self, "Template File Opened", 
                f"Template file opened in default editor:\n{template_path}\n\n"
                "After editing, click 'Load from File' to refresh the interface."
            )
        
        except Exception as e:
            QMessageBox.warning(self, "Error Opening File", f"Could not open template file:\n{e}")


class FolderEditDialog(QDialog):
    """Dialog for editing folder name and description"""
    
    def __init__(self, parent, title, name="", description=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(500, 200)
        
        # Apply styling
        self.setStyleSheet(ResolveTheme.get_main_stylesheet())
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Form layout
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(12)
        form_layout.setHorizontalSpacing(12)
        
        # Name field
        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        self.name_edit.setPlaceholderText("Enter folder name (e.g., 'comp', 'reference')")
        form_layout.addRow("Folder Name:", self.name_edit)
        
        # Description field
        self.description_edit = QLineEdit()
        self.description_edit.setText(description)
        self.description_edit.setPlaceholderText("Enter description (e.g., 'Compositing work files')")
        form_layout.addRow("Description:", self.description_edit)
        
        layout.addLayout(form_layout)
        
        # Validation info
        info_label = QLabel("• Folder names should be lowercase with no spaces\n• Use underscores for multiple words (e.g., 'work_files')")
        info_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 8px;")
        layout.addWidget(info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("OK")
        ok_btn.setProperty("class", "primary-button")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # Focus and validation
        self.name_edit.setFocus()
        self.name_edit.textChanged.connect(self.validate_input)
        self.validate_input()
    
    def validate_input(self):
        """Validate folder name input"""
        name = self.name_edit.text().strip()
        
        # Find OK button and enable/disable
        for button in self.findChildren(QPushButton):
            if button.text() == "OK":
                button.setEnabled(bool(name))
                break
    
    def get_values(self):
        """Get the entered name and description"""
        return self.name_edit.text().strip(), self.description_edit.text().strip()


# UPDATE the main GUI class to add the folder structure tab:
def add_folder_structure_tab_to_gui(self):
    """Add this method to your UniversalCompGUI class"""
    
    # In your create_left_panel method, after creating the tab widget, add:
    
    # Create folder structure tab
    folder_tab = FolderStructureTab(self.generator.settings_manager)
    tab_widget.addTab(folder_tab, "Folder Structure")
    
    # Store reference for saving settings
    self.folder_structure_tab = folder_tab

# UPDATE the save_settings method in UniversalCompGUI:
def update_save_settings_for_folder_tab(self):
    """Add this to your save_settings method"""
    
    # Add this line in your save_settings method:
    if hasattr(self, 'folder_structure_tab'):
        # The folder structure tab saves its own settings when user clicks "Save Changes"
        # But we need to ensure the main enable setting is synced
        main_enabled = self.generator.settings_manager.get_setting("create_folder_structure")
        if hasattr(self, 'create_folders_check'):
            self.create_folders_check.setChecked(main_enabled)


class FolderStructureDialog(QDialog):
    """Dialog for configuring folder structure template"""

    def __init__(self, parent, settings_manager):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.folder_manager = settings_manager.folder_manager
        self.init_ui()
        self.load_template()

    def init_ui(self):
        self.setWindowTitle("Configure Folder Structure")
        self.setModal(True)
        self.resize(800, 600)

        # Apply Resolve styling
        self.setStyleSheet(ResolveTheme.get_main_stylesheet())

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("Shot Folder Structure Configuration")
        title.setProperty("class", "title-label")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Main content in horizontal layout
        main_layout = QHBoxLayout()
        main_layout.setSpacing(20)

        # Left side - Configuration
        left_panel = self.create_config_panel()
        main_layout.addWidget(left_panel, 1)

        # Right side - Preview
        right_panel = self.create_preview_panel()
        main_layout.addWidget(right_panel, 1)

        layout.addLayout(main_layout)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        open_template_btn = QPushButton("📝 Edit Template JSON")
        open_template_btn.setToolTip("Open the folder structure template JSON file in your default editor")
        open_template_btn.clicked.connect(self.open_template_file)
        button_layout.addWidget(open_template_btn)

        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self.reset_to_default)
        button_layout.addWidget(reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Apply Changes")
        ok_btn.setProperty("class", "primary-button")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

    def create_config_panel(self):
        """Create the left configuration panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Enable/Disable checkbox
        self.enable_folders_check = QCheckBox("Create folder structure when generating comp files")
        self.enable_folders_check.setChecked(True)
        self.enable_folders_check.setToolTip("Enable automatic folder structure creation")
        self.enable_folders_check.toggled.connect(self.update_preview)
        layout.addWidget(self.enable_folders_check)

        # Template info
        template_group = QGroupBox("Current Template")
        template_layout = QVBoxLayout(template_group)

        self.template_info_label = QLabel()
        self.template_info_label.setWordWrap(True)
        self.template_info_label.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        template_layout.addWidget(self.template_info_label)

        # Template file path
        self.template_path_label = QLabel()
        self.template_path_label.setProperty("class", "path-label")
        self.template_path_label.setWordWrap(True)
        template_layout.addWidget(self.template_path_label)

        layout.addWidget(template_group)

        # Quick presets
        presets_group = QGroupBox("Quick Presets")
        presets_layout = QVBoxLayout(presets_group)

        presets_desc = QLabel("Reset template to common folder structures:")
        presets_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        presets_layout.addWidget(presets_desc)

        preset_buttons_layout = QHBoxLayout()
        preset_buttons_layout.setSpacing(8)

        default_preset_btn = QPushButton("VFX Standard")
        default_preset_btn.setProperty("class", "small-button")
        default_preset_btn.setToolTip("Standard VFX folder structure with comp, plate, reference, tracking, roto")
        default_preset_btn.clicked.connect(self.apply_vfx_preset)
        preset_buttons_layout.addWidget(default_preset_btn)

        minimal_preset_btn = QPushButton("Minimal")
        minimal_preset_btn.setProperty("class", "small-button")
        minimal_preset_btn.setToolTip("Minimal structure with just comp and reference folders")
        minimal_preset_btn.clicked.connect(self.apply_minimal_preset)
        preset_buttons_layout.addWidget(minimal_preset_btn)

        preset_buttons_layout.addStretch()
        presets_layout.addLayout(preset_buttons_layout)

        layout.addWidget(presets_group)

        # Instructions
        instructions_group = QGroupBox("Instructions")
        instructions_layout = QVBoxLayout(instructions_group)

        instructions_text = QLabel("""• Use "Edit Template JSON" to customize the folder structure
• The template is stored as JSON and can be edited with any text editor
• Changes take effect immediately when you click "Apply Changes"
• Each shot will get its own copy of this folder structure
• Folders are created relative to the shot directory (<shotdir>)""")
        instructions_text.setStyleSheet("color: #b0b0b0; font-size: 11px; line-height: 1.4;")
        instructions_text.setWordWrap(True)
        instructions_layout.addWidget(instructions_text)

        layout.addWidget(instructions_group)

        layout.addStretch()
        return panel

    def create_preview_panel(self):
        """Create the right preview panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        preview_label = QLabel("Folder Structure Preview")
        preview_label.setProperty("class", "section-title")
        layout.addWidget(preview_label)

        preview_desc = QLabel("Folders that will be created in each shot directory:")
        preview_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        layout.addWidget(preview_desc)

        # Preview tree widget
        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderLabel("Folder Structure")
        self.preview_tree.setAlternatingRowColors(True)
        self.preview_tree.setRootIsDecorated(True)
        layout.addWidget(self.preview_tree)

        # Statistics
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 8px;")
        layout.addWidget(self.stats_label)

        return panel

    def load_template(self):
        """Load current template and update UI"""
        try:
            template = self.folder_manager.load_folder_template()
            
            # Update enable checkbox
            self.enable_folders_check.setChecked(template.get('enabled', True))
            
            # Update template info
            description = template.get('description', 'No description')
            self.template_info_label.setText(f"Description: {description}")
            
            # Update template path
            template_path = self.folder_manager.get_template_file_path()
            self.template_path_label.setText(f"Template file: {template_path}")
            
            # Update preview
            self.update_preview()
            
        except Exception as e:
            QMessageBox.warning(self, "Error Loading Template", f"Could not load folder template:\n{e}")

    def update_preview(self):
        """Update the folder structure preview"""
        try:
            self.preview_tree.clear()
            
            if not self.enable_folders_check.isChecked():
                disabled_item = QTreeWidgetItem(["📁 Folder structure creation disabled"])
                disabled_item.setForeground(0, QColor("#666"))
                self.preview_tree.addTopLevelItem(disabled_item)
                self.stats_label.setText("Folder structure creation is disabled")
                return
            
            template = self.folder_manager.load_folder_template()
            folder_structure = template.get('folder_structure', {})
            
            if not folder_structure:
                empty_item = QTreeWidgetItem(["📁 No folders defined in template"])
                empty_item.setForeground(0, QColor("#888"))
                self.preview_tree.addTopLevelItem(empty_item)
                self.stats_label.setText("No folders defined")
                return
            
            # Add example shot root
            root_item = QTreeWidgetItem([f"📁 example_shot_sh0010/ (Shot Directory)"])
            root_item.setExpanded(True)
            self.preview_tree.addTopLevelItem(root_item)
            
            folder_count = 0
            
            # Add each main folder and its subfolders
            for main_folder, config in folder_structure.items():
                description = config.get('description', '')
                main_item = QTreeWidgetItem([f"📁 {main_folder}/"])
                if description:
                    main_item.setToolTip(0, description)
                main_item.setExpanded(True)
                root_item.addChild(main_item)
                folder_count += 1
                
                # Add subfolders
                subfolders = config.get('subfolders', {})
                for subfolder_name, subfolder_desc in subfolders.items():
                    sub_item = QTreeWidgetItem([f"📁 {subfolder_name}/"])
                    if subfolder_desc:
                        sub_item.setToolTip(0, subfolder_desc)
                    main_item.addChild(sub_item)
                    folder_count += 1
            
            # Update stats
            main_folder_count = len(folder_structure)
            self.stats_label.setText(f"{folder_count} total folders ({main_folder_count} main folders)")
            
        except Exception as e:
            error_item = QTreeWidgetItem([f"❌ Error loading template: {e}"])
            error_item.setForeground(0, QColor("#f44336"))
            self.preview_tree.addTopLevelItem(error_item)
            self.stats_label.setText("Error loading template")

    def open_template_file(self):
        """Open the template JSON file in the default editor"""
        try:
            import subprocess
            template_path = self.folder_manager.get_template_file_path()
            
            # Ensure the template file exists
            if not template_path.exists():
                # Create default template if it doesn't exist
                template = self.folder_manager.load_folder_template()
                self.folder_manager.save_folder_template(template)
            
            # Platform-specific file opening
            system = platform.system()
            
            if system == "Windows":
                os.startfile(str(template_path))
            elif system == "Darwin":  # macOS
                subprocess.call(["open", str(template_path)])
            else:  # Linux and others
                subprocess.call(["xdg-open", str(template_path)])
            
            QMessageBox.information(self, "Template File Opened", 
                                  f"Template file opened in default editor:\n{template_path}\n\n"
                                  "After editing, close and reopen this dialog to see changes.")
            
        except Exception as e:
            QMessageBox.warning(self, "Error Opening Template", f"Could not open template file:\n{e}")

    def apply_vfx_preset(self):
        """Apply VFX standard preset - RECURSIVE VERSION"""
        reply = QMessageBox.question(
            self, "Apply VFX Preset", 
            "Replace current folder structure with VFX Standard preset?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.description_edit.setText("Standard VFX folder structure with comprehensive organization")
            self.enable_folders_check.setChecked(True)
            
            # Clear and populate with VFX preset
            self.folder_tree.clear()
            
            # New format: (name, description, [(subfolder_name, subfolder_desc, [nested_subfolders])])
            vfx_structure = [
                ("comp", "Compositing files and renders", [
                    ("work", "Working composition files", []),
                    ("render", "Final renders", [
                        ("final", "Approved final renders", []),
                        ("wip", "Work in progress renders", []),
                        ("daily", "Daily review renders", [])
                    ]),
                    ("preview", "Preview renders and dailies", []),
                    ("elements", "Individual elements and passes", [])
                ]),
                ("plate", "Original plates and footage", [
                    ("original", "Untouched original footage", []),
                    ("conform", "Conformed and processed plates", []),
                    ("temp", "Temporary plate processing", [])
                ]),
                ("reference", "Reference materials and assets", [
                    ("images", "Reference images and stills", []),
                    ("video", "Reference video clips", []),
                    ("assets", "3D assets and models", [])
                ]),
                ("tracking", "Camera tracking and matchmove data", [
                    ("data", "Tracking data files", []),
                    ("export", "Exported tracking information", [])
                ]),
                ("roto", "Rotoscoping and masking work", [
                    ("work", "Work-in-progress roto files", []),
                    ("final", "Final approved roto shapes", [])
                ])
            ]
            
            self._populate_tree_from_structure(vfx_structure)
            self.on_template_changed()

    def apply_minimal_preset(self):
        """Apply minimal preset - RECURSIVE VERSION"""
        reply = QMessageBox.question(
            self, "Apply Minimal Preset", 
            "Replace current folder structure with Minimal preset?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.description_edit.setText("Minimal folder structure for simple projects")
            self.enable_folders_check.setChecked(True)
            
            # Clear and populate with minimal preset
            self.folder_tree.clear()
            
            minimal_structure = [
                ("comp", "Compositing files and renders", [
                    ("work", "Working composition files", []),
                    ("render", "Final renders", [])
                ]),
                ("reference", "Reference materials", [
                    ("images", "Reference images", []),
                    ("video", "Reference video", [])
                ])
            ]
            
            self._populate_tree_from_structure(minimal_structure)
            self.on_template_changed()

    def reset_to_default(self):
        """Reset to default template"""
        reply = QMessageBox.question(self, "Reset Template", 
                                   "Reset folder structure template to default?\n\nThis will overwrite any custom changes.",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.folder_manager.save_folder_template(self.folder_manager.default_template)
            self.load_template()
            QMessageBox.information(self, "Template Reset", "Template reset to default successfully!")

    def accept(self):
        """Save settings when OK is clicked"""
        try:
            # Update the enabled setting in the template
            template = self.folder_manager.load_folder_template()
            template['enabled'] = self.enable_folders_check.isChecked()
            self.folder_manager.save_folder_template(template)
            
            # Also update the main settings
            self.settings_manager.set_setting("create_folder_structure", self.enable_folders_check.isChecked())
            self.settings_manager.save_settings()
            
            super().accept()
            
        except Exception as e:
            QMessageBox.warning(self, "Error Saving", f"Could not save folder structure settings:\n{e}")


# GUI Integration Methods for Main Window
def add_folder_structure_to_gui(self):
    """Add folder structure settings to the main GUI - to be integrated into create_comp_creation_tab"""
    
    # Add this to the comp creation tab layout after EXR settings
    folder_group = QGroupBox("Shot Folder Structure")
    folder_layout = QVBoxLayout(folder_group)
    folder_layout.setSpacing(12)

    folder_desc = QLabel("Automatically create folder structure for each shot:")
    folder_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
    folder_layout.addWidget(folder_desc)

    self.create_folders_check = QCheckBox("Create shot folder structure")
    self.create_folders_check.setChecked(True)
    self.create_folders_check.setToolTip("Create additional folders based on JSON template")
    folder_layout.addWidget(self.create_folders_check)

    # Preview/configuration button
    folder_button_layout = QHBoxLayout()
    
    self.folder_preview_label = QLabel("Loading template...")
    self.folder_preview_label.setStyleSheet("color: #888; font-size: 11px;")
    folder_button_layout.addWidget(self.folder_preview_label)
    
    folder_button_layout.addStretch()
    
    configure_folders_btn = QPushButton("Configure Structure")
    configure_folders_btn.setProperty("class", "small-button")
    configure_folders_btn.setToolTip("Configure which folders are created for each shot")
    configure_folders_btn.clicked.connect(self.configure_folder_structure)
    folder_button_layout.addWidget(configure_folders_btn)
    
    folder_layout.addLayout(folder_button_layout)

    return folder_group

def configure_folder_structure(self):
    """Open folder structure configuration dialog"""
    dialog = FolderStructureDialog(self, self.generator.settings_manager)
    dialog.exec()
    
    # Update preview label after dialog closes
    self.update_folder_preview()

def update_folder_preview(self):
    """Update folder structure preview label"""
    try:
        if hasattr(self, 'create_folders_check') and hasattr(self, 'folder_preview_label'):
            if self.create_folders_check.isChecked():
                template = self.generator.settings_manager.folder_manager.load_folder_template()
                if template.get('enabled', True):
                    folder_list = self.generator.settings_manager.folder_manager.get_folder_list(template)
                    folder_count = len(folder_list)
                    main_folders = len(template.get('folder_structure', {}))
                    self.folder_preview_label.setText(f"{folder_count} folders ({main_folders} main) per shot")
                else:
                    self.folder_preview_label.setText("Folder creation disabled in template")
            else:
                self.folder_preview_label.setText("Folder creation disabled")
    except Exception as e:
        if hasattr(self, 'folder_preview_label'):
            self.folder_preview_label.setText("Error loading template")
        print(f"Error updating folder preview: {e}")

def load_folder_structure_settings(self):
    """Load folder structure settings - to be added to load_settings method"""
    
    # Load folder structure setting
    create_folders = self.generator.settings_manager.get_setting("create_folder_structure")
    if hasattr(self, 'create_folders_check'):
        self.create_folders_check.setChecked(create_folders)
    
    # Update preview
    self.update_folder_preview()

def save_folder_structure_settings(self):
    """Save folder structure settings - to be added to save_settings method"""
    
    if hasattr(self, 'create_folders_check'):
        self.generator.settings_manager.set_setting("create_folder_structure", self.create_folders_check.isChecked())

class UniversalCompGUI(QMainWindow):
    """Universal Comp Generator GUI supporting both Fusion and Nuke with VFX Notes and configurable color management"""

    def __init__(self):
        super().__init__()
        self.generator = CompDeploy()
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("CompDeploy v1.0")
        self.setGeometry(100, 100, 1650, 1150)  # Wider for side-by-side layout, shorter height
        self.setMinimumSize(1580, 1050)  # Wider minimum, reduced height

        # Apply Resolve theme
        self.setStyleSheet(ResolveTheme.get_main_stylesheet())

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main horizontal layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left panel - Settings
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel, 2)

        # Right panel - Output and controls
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel, 1)

        # Initial refresh
        self.refresh_selection()

    def create_left_panel(self):
        """Create the left settings panel with tabs"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title_layout = QHBoxLayout()
        title = QLabel("CompDeploy")
        title.setProperty("class", "title-label")
        title_layout.addWidget(title)
        title_layout.addStretch()

        version_label = QLabel("v1.0")
        version_label.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        title_layout.addWidget(version_label)
        layout.addLayout(title_layout)

        # Create tab widget
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                background: #2a2a2a;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #404040;
                color: #cccccc;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                min-width: 100px;
            }
            QTabBar::tab:selected {
                background: #4376A1;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background: #4a4a4a;
            }
        """)

        # Tab 1: Comp Creation
        comp_tab = self.create_comp_creation_tab()
        tab_widget.addTab(comp_tab, "Comp Creation")

        # Tab 2: Paths (NEW)
        paths_tab = self.create_paths_tab()
        tab_widget.addTab(paths_tab, "Paths")

        # Tab 3: OCIO
        ocio_tab = self.create_ocio_tab()
        tab_widget.addTab(ocio_tab, "OCIO")

        # Tab 4: Folder Structure
        folder_tab = FolderStructureTab(self.generator.settings_manager)
        folder_tab.main_window = self
        tab_widget.addTab(folder_tab, "Folder Structure")
        self.folder_structure_tab = folder_tab

        layout.addWidget(tab_widget)

        # Debug options (independent from tabs)
        debug_group = QGroupBox("Debug Options")
        debug_layout = QVBoxLayout(debug_group)

        self.debug_check = QCheckBox("Enable detailed debug output")
        debug_layout.addWidget(self.debug_check)

        self.create_test_notes_check = QCheckBox("Create test notes if none found")
        self.create_test_notes_check.setToolTip("Creates sample VFX notes for testing when no real notes are detected")
        debug_layout.addWidget(self.create_test_notes_check)

        self.generate_scene_report_check = QCheckBox("Generate scene report JSON")
        self.generate_scene_report_check.setChecked(True)
        self.generate_scene_report_check.setToolTip("Create comprehensive JSON report with all clip metadata and generation results")
        debug_layout.addWidget(self.generate_scene_report_check)

        # Settings folder button
        settings_folder_layout = QHBoxLayout()
        settings_folder_layout.addStretch()

        open_settings_btn = QPushButton("📁 Settings Folder")
        open_settings_btn.setProperty("class", "small-button")
        open_settings_btn.setStyleSheet("font-size: 10px; color: #888; padding: 4px 8px;")
        open_settings_btn.setToolTip("Open folder containing settings.json configuration file")
        open_settings_btn.clicked.connect(self.open_settings_folder)
        settings_folder_layout.addWidget(open_settings_btn)

        debug_layout.addLayout(settings_folder_layout)

        layout.addWidget(debug_group)
        layout.addStretch()
        return panel
    
    def configure_folder_structure(self):
        """Open folder structure configuration dialog"""
        dialog = FolderStructureDialog(self, self.generator.settings_manager)
        dialog.exec()
        self.update_folder_preview()

    def update_folder_preview(self):
        """Update folder structure preview label"""
        try:
            if hasattr(self, 'create_folders_check') and hasattr(self, 'folder_preview_label'):
                if self.create_folders_check.isChecked():
                    template = self.generator.settings_manager.folder_manager.load_folder_template()
                    if template.get('enabled', True):
                        folder_list = self.generator.settings_manager.folder_manager.get_folder_list(template)
                        folder_count = len(folder_list)
                        main_folders = len(template.get('folder_structure', {}))
                        self.folder_preview_label.setText(f"{folder_count} folders ({main_folders} main) per shot")
                    else:
                        self.folder_preview_label.setText("Folder creation disabled in template")
                else:
                    self.folder_preview_label.setText("Folder creation disabled")
        except Exception as e:
            if hasattr(self, 'folder_preview_label'):
                self.folder_preview_label.setText("Error loading template")

    def create_comp_creation_tab(self):
        """Create the Comp Creation tab - formats, sequence mode, and VFX notes"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Output Formats & Sequence Mode - Horizontal layout
        format_sequence_layout = QHBoxLayout()
        format_sequence_layout.setSpacing(16)

        # Output Formats Section (Left side)
        format_group = QGroupBox("Output Formats")
        format_layout = QVBoxLayout(format_group)
        format_layout.setSpacing(12)

        format_desc = QLabel("Choose which starting scripts to generate:")
        format_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        format_layout.addWidget(format_desc)

        # Main comp files
        main_comps_label = QLabel("Main Compositing:")
        main_comps_label.setStyleSheet("font-weight: bold; color: #4376A1; margin-top: 4px;")
        format_layout.addWidget(main_comps_label)

        self.fusion_check = QCheckBox("Generate Fusion Studio files (.comp)")
        self.fusion_check.setChecked(True)
        self.fusion_check.setToolTip("Create Fusion Studio composition files")
        format_layout.addWidget(self.fusion_check)

        self.nuke_check = QCheckBox("Generate Nuke scripts (.nk)")
        self.nuke_check.setChecked(False)
        self.nuke_check.setToolTip("Create Foundry Nuke script files")
        format_layout.addWidget(self.nuke_check)

        # Specialized Fusion comps
        specialized_label = QLabel("Specialized Fusion Comps:")
        specialized_label.setStyleSheet("font-weight: bold; color: #F9423F; margin-top: 12px;")
        format_layout.addWidget(specialized_label)

        self.fusion_depth_check = QCheckBox("Depth extraction (.comp)")
        self.fusion_depth_check.setChecked(False)
        self.fusion_depth_check.setToolTip("Create Fusion comp with DepthMap node for depth extraction")
        format_layout.addWidget(self.fusion_depth_check)

        self.fusion_mmask_check = QCheckBox("Magic Mask generation (.comp)")
        self.fusion_mmask_check.setChecked(False)
        self.fusion_mmask_check.setToolTip("Create Fusion comp with MagicMask node for rotoscoping")
        format_layout.addWidget(self.fusion_mmask_check)

        # Overwrite setting
        self.overwrite_check = QCheckBox("Overwrite existing files")
        self.overwrite_check.setChecked(False)
        self.overwrite_check.setToolTip("If unchecked, creates next available version independently for each format")
        self.overwrite_check.setStyleSheet("margin-top: 12px;")
        format_layout.addWidget(self.overwrite_check)

        format_sequence_layout.addWidget(format_group, 1)

        # Sequence Mode Settings (Right side)
        sequence_group = QGroupBox("Sequence Mode")
        sequence_layout = QVBoxLayout(sequence_group)
        sequence_layout.setSpacing(12)

        # Mode selection
        mode_desc = QLabel("Choose sequence naming strategy:")
        mode_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        sequence_layout.addWidget(mode_desc)

        self.versioned_sequences_radio = QRadioButton("Versioned sequences (v001, v002, v003...)")
        self.versioned_sequences_radio.setChecked(True)
        self.versioned_sequences_radio.setToolTip("Generate separate sequence folders for each version")
        sequence_layout.addWidget(self.versioned_sequences_radio)

        self.single_sequence_radio = QRadioButton("Single sequence (v999) with metadata injection")
        self.single_sequence_radio.setChecked(False)
        self.single_sequence_radio.setToolTip("Generate single sequence folder with comp version as EXR metadata")
        sequence_layout.addWidget(self.single_sequence_radio)

        # Metadata injection settings
        metadata_widget = QWidget()
        metadata_layout = QVBoxLayout(metadata_widget)
        metadata_layout.setContentsMargins(20, 8, 0, 0)

        self.metadata_injection_check = QCheckBox("Inject comp version as EXR metadata")
        self.metadata_injection_check.setChecked(True)
        self.metadata_injection_check.setToolTip("Add comp file version to EXR metadata for tracking")
        metadata_layout.addWidget(self.metadata_injection_check)

        # Metadata field name
        field_layout = QHBoxLayout()
        field_label = QLabel("Field name:")
        field_label.setStyleSheet("color: #b0b0b0; font-size: 12px; min-width: 70px;")
        field_layout.addWidget(field_label)

        self.metadata_field_edit = QLineEdit()
        self.metadata_field_edit.setText("shoot_scene_take")
        self.metadata_field_edit.setPlaceholderText("e.g., shoot_scene_take, comp_version, version")
        self.metadata_field_edit.setToolTip("Metadata field name for comp version")
        field_layout.addWidget(self.metadata_field_edit)

        metadata_layout.addLayout(field_layout)
        sequence_layout.addWidget(metadata_widget)

        # Enable/disable metadata controls based on radio selection
        def on_sequence_mode_changed():
            is_single_mode = self.single_sequence_radio.isChecked()
            metadata_widget.setEnabled(is_single_mode)
            
        self.versioned_sequences_radio.toggled.connect(on_sequence_mode_changed)
        self.single_sequence_radio.toggled.connect(on_sequence_mode_changed)
        on_sequence_mode_changed()

        format_sequence_layout.addWidget(sequence_group, 1)
        layout.addLayout(format_sequence_layout)

        # VFX Notes Settings
        notes_group = QGroupBox("VFX Notes")
        notes_layout = QVBoxLayout(notes_group)
        notes_layout.setSpacing(12)

        notes_desc = QLabel("Extract and include notes from clip metadata:")
        notes_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        notes_layout.addWidget(notes_desc)

        self.include_notes_check = QCheckBox("Include media clip comments as StickyNotes")
        self.include_notes_check.setChecked(True)
        self.include_notes_check.setToolTip("Extract notes from Comments and Description fields in clip metadata")
        notes_layout.addWidget(self.include_notes_check)

        # Notes position
        position_layout = QHBoxLayout()
        position_label = QLabel("Position:")
        position_label.setStyleSheet("min-width: 70px;")
        position_layout.addWidget(position_label)

        self.notes_position_combo = QComboBox()
        self.notes_position_combo.addItems(["Above Loaders", "Right Side"])
        self.notes_position_combo.setCurrentText("Above Loaders")
        self.notes_position_combo.setEnabled(True)
        position_layout.addWidget(self.notes_position_combo)
        position_layout.addStretch()

        notes_layout.addLayout(position_layout)
        self.include_notes_check.toggled.connect(self.notes_position_combo.setEnabled)

        layout.addWidget(notes_group)

        layout.addStretch()
        return tab_widget
    
    def create_paths_tab(self):
        """Create the Paths tab - output paths and EXR settings"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Output Path Settings
        path_group = QGroupBox("Output Path Settings")
        path_layout = QVBoxLayout(path_group)

        path_desc = QLabel("Configure where script files and render outputs are generated:")
        path_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        path_layout.addWidget(path_desc)

        # Script Paths Section
        script_paths_label = QLabel("Script File Paths:")
        script_paths_label.setStyleSheet("font-size: 13px; font-weight: bold; margin-top: 8px; color: #4376A1;")
        path_layout.addWidget(script_paths_label)

        # Fusion script path
        fusion_script_label = QLabel("Fusion Scripts:")
        fusion_script_label.setStyleSheet("font-size: 12px; font-weight: bold; margin-top: 4px;")
        path_layout.addWidget(fusion_script_label)

        self.current_fusion_script_label = QLabel()
        self.current_fusion_script_label.setProperty("class", "path-label")
        self.current_fusion_script_label.setWordWrap(True)
        path_layout.addWidget(self.current_fusion_script_label)

        # Nuke script path
        nuke_script_label = QLabel("Nuke Scripts:")
        nuke_script_label.setStyleSheet("font-size: 12px; font-weight: bold; margin-top: 4px;")
        path_layout.addWidget(nuke_script_label)

        self.current_nuke_script_label = QLabel()
        self.current_nuke_script_label.setProperty("class", "path-label")
        self.current_nuke_script_label.setWordWrap(True)
        path_layout.addWidget(self.current_nuke_script_label)

        # Render Paths Section
        render_paths_label = QLabel("Render Output Paths:")
        render_paths_label.setStyleSheet("font-size: 13px; font-weight: bold; margin-top: 12px; color: #F9423F;")
        path_layout.addWidget(render_paths_label)

        # Fusion render path
        fusion_render_label = QLabel("Fusion Renders:")
        fusion_render_label.setStyleSheet("font-size: 12px; font-weight: bold; margin-top: 4px;")
        path_layout.addWidget(fusion_render_label)

        self.current_fusion_render_label = QLabel()
        self.current_fusion_render_label.setProperty("class", "path-label")
        self.current_fusion_render_label.setWordWrap(True)
        path_layout.addWidget(self.current_fusion_render_label)

        # Nuke render path
        nuke_render_label = QLabel("Nuke Renders:")
        nuke_render_label.setStyleSheet("font-size: 12px; font-weight: bold; margin-top: 4px;")
        path_layout.addWidget(nuke_render_label)

        self.current_nuke_render_label = QLabel()
        self.current_nuke_render_label.setProperty("class", "path-label")
        self.current_nuke_render_label.setWordWrap(True)
        path_layout.addWidget(self.current_nuke_render_label)

        # Edit paths button
        edit_path_btn = QPushButton("Customize All Paths")
        edit_path_btn.setProperty("class", "primary-button")
        edit_path_btn.clicked.connect(self.edit_output_paths)
        edit_path_btn.setToolTip("Configure script and render output paths")
        path_layout.addWidget(edit_path_btn)

        layout.addWidget(path_group)

        # EXR Export Settings
        exr_group = QGroupBox("EXR Export Settings")
        exr_layout = QFormLayout(exr_group)
        exr_layout.setVerticalSpacing(10)
        exr_layout.setHorizontalSpacing(12)

        exr_desc = QLabel("Configure EXR compression and bit depth for renders:")
        exr_desc.setStyleSheet("color: #b0b0b0; font-size: 12px;")
        exr_layout.addRow("", exr_desc)

        # Compression
        self.compression_combo = QComboBox()
        self.compression_combo.addItems([
            "None", "RLE", "ZIPS", "ZIP",
            "PIZ", "PXR24", "B44", "B44A", "DWAA", "DWAB"
        ])
        self.compression_combo.setCurrentText("PIZ")
        self.compression_combo.currentTextChanged.connect(self.on_compression_changed)
        exr_layout.addRow("Compression:", self.compression_combo)

        # Bit Depth
        self.bit_depth_combo = QComboBox()
        self.bit_depth_combo.addItems(["16-bit Float", "32-bit Float"])
        self.bit_depth_combo.setCurrentText("16-bit Float")
        exr_layout.addRow("Bit Depth:", self.bit_depth_combo)

        # Quality (only for DWAA/DWAB)
        self.quality_label = QLabel("DWA Quality:")
        quality_layout = QHBoxLayout()
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(0, 100)
        self.quality_spin.setValue(45)
        self.quality_spin.setMinimumWidth(80)
        self.quality_spin.setToolTip("Quality level for DWAA/DWAB compression (lower = better quality)")
        quality_layout.addWidget(self.quality_spin)
        quality_layout.addStretch()

        self.quality_label.setVisible(False)
        self.quality_spin.setVisible(False)

        exr_layout.addRow(self.quality_label, quality_layout)

        layout.addWidget(exr_group)

        folder_group = QGroupBox("Shot Folder Structure")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(12)

        folder_desc = QLabel("Automatically create folder structure for each shot:")
        folder_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        folder_layout.addWidget(folder_desc)

        self.create_folders_check = QCheckBox("Create shot folder structure")
        self.create_folders_check.setChecked(True)
        self.create_folders_check.setToolTip("Create additional folders based on JSON template")
        self.create_folders_check.toggled.connect(self.update_folder_preview)
        self.create_folders_check.toggled.connect(self.on_create_folders_toggled)

        # Preview/configuration button
        folder_button_layout = QHBoxLayout()
        
        self.folder_preview_label = QLabel("Loading template...")
        self.folder_preview_label.setStyleSheet("color: #888; font-size: 11px;")
        folder_button_layout.addWidget(self.folder_preview_label)
        
        folder_button_layout.addStretch()
        
        configure_folders_btn = QPushButton("Configure Structure")
        configure_folders_btn.setProperty("class", "small-button")
        configure_folders_btn.setToolTip("Configure which folders are created for each shot")
        configure_folders_btn.clicked.connect(self.configure_folder_structure)
        folder_button_layout.addWidget(configure_folders_btn)
        
        folder_layout.addLayout(folder_button_layout)
        
        layout.addWidget(folder_group)

        layout.addStretch()
        return tab_widget
    
    def on_create_folders_toggled(self, checked):
        """Immediately save folder creation state when toggled"""
        print(f"[DEBUG] Checkbox toggled to: {checked}")

        # Save to settings only (not template)
        self.generator.settings_manager.set_setting("create_folder_structure", checked)
        self.generator.settings_manager.save_settings()
        
        # Verify it was saved
        saved_value = self.generator.settings_manager.get_setting("create_folder_structure")
        print(f"[DEBUG] Saved and verified as: {saved_value}")
        
        self.update_folder_preview()
        
        # Sync with Folder Structure tab if it exists
        if hasattr(self, 'folder_structure_tab'):
            self.folder_structure_tab.enable_folders_check.blockSignals(True)
            self.folder_structure_tab.enable_folders_check.setChecked(checked)
            self.folder_structure_tab.enable_folders_check.blockSignals(False)
            self.folder_structure_tab.update_preview()

    def create_ocio_tab(self):
        """Create the OCIO tab content"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)

        # Nuke Color Management Section
        color_group = QGroupBox("Nuke Color Management")
        color_layout = QVBoxLayout(color_group)
        color_layout.setSpacing(12)

        # Description
        color_desc = QLabel("Configure color management for Nuke scripts:")
        color_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        color_layout.addWidget(color_desc)

        # Color management type selector
        color_type_layout = QHBoxLayout()
        color_mgmt_label = QLabel("Color Management:")
        color_mgmt_label.setStyleSheet("color: #cccccc; font-size: 13px; min-width: 120px;")
        color_type_layout.addWidget(color_mgmt_label)

        self.nuke_color_combo = QComboBox()
        self.nuke_color_combo.addItems(["ACES 1.2 (Built-in)", "Nuke Rec709", "Custom OCIO Config"])
        self.nuke_color_combo.setCurrentText("ACES 1.2 (Built-in)")
        self.nuke_color_combo.setToolTip("Choose color management system for Nuke scripts")
        self.nuke_color_combo.currentTextChanged.connect(self.on_color_management_changed)
        color_type_layout.addWidget(self.nuke_color_combo)
        color_type_layout.addStretch()

        color_layout.addLayout(color_type_layout)

        layout.addWidget(color_group)

        # Custom OCIO Settings
        self.custom_ocio_widget = QWidget()
        custom_ocio_layout = QVBoxLayout(self.custom_ocio_widget)
        custom_ocio_layout.setContentsMargins(0, 0, 0, 0)

        ocio_group = QGroupBox("Custom OCIO Configuration")
        ocio_layout = QVBoxLayout(ocio_group)
        ocio_layout.setSpacing(12)

        # OCIO config file selection
        ocio_file_layout = QHBoxLayout()
        ocio_file_label = QLabel("OCIO Config File:")
        ocio_file_label.setStyleSheet("color: #cccccc; font-size: 13px; min-width: 100px;")
        ocio_file_layout.addWidget(ocio_file_label)

        self.ocio_path_edit = QLineEdit()
        self.ocio_path_edit.setPlaceholderText("Select .ocio configuration file...")
        self.ocio_path_edit.setReadOnly(True)
        ocio_file_layout.addWidget(self.ocio_path_edit)

        self.browse_ocio_btn = QPushButton("Browse")
        self.browse_ocio_btn.setProperty("class", "small-button")
        self.browse_ocio_btn.clicked.connect(self.browse_ocio_config)
        ocio_file_layout.addWidget(self.browse_ocio_btn)

        ocio_layout.addLayout(ocio_file_layout)

        # OCIO settings grid
        ocio_settings_layout = QFormLayout()
        ocio_settings_layout.setHorizontalSpacing(12)
        ocio_settings_layout.setVerticalSpacing(10)

        # Plate Color Space (separate from working space)
        self.plate_colorspace_combo = QComboBox()
        self.plate_colorspace_combo.setToolTip("Colorspace of input plates (for Read and Write nodes)")
        ocio_settings_layout.addRow("Plate Color Space:", self.plate_colorspace_combo)

        # Working Space
        self.working_space_combo = QComboBox()
        self.working_space_combo.setToolTip("Colorspace for internal processing (scene_linear, ACEScg, etc.)")
        ocio_settings_layout.addRow("Working Space:", self.working_space_combo)

        # Display
        self.display_combo = QComboBox()
        self.display_combo.setToolTip("Display device for Write node")
        self.display_combo.currentTextChanged.connect(self.on_display_changed)
        ocio_settings_layout.addRow("Display:", self.display_combo)

        # View
        self.view_combo = QComboBox()
        self.view_combo.setToolTip("View transform for Write node")
        ocio_settings_layout.addRow("View:", self.view_combo)

        # Viewer Process
        self.viewer_process_combo = QComboBox()
        self.viewer_process_combo.setToolTip("Display transform for Viewer node")
        ocio_settings_layout.addRow("Viewer Process:", self.viewer_process_combo)

        ocio_layout.addLayout(ocio_settings_layout)

        # Status label for OCIO parsing
        self.ocio_status_label = QLabel()
        self.ocio_status_label.setStyleSheet("color: #888; font-size: 10px; margin-top: 8px;")
        self.ocio_status_label.setWordWrap(True)
        ocio_layout.addWidget(self.ocio_status_label)

        ocio_group.setLayout(ocio_layout)
        custom_ocio_layout.addWidget(ocio_group)

        self.custom_ocio_widget.setVisible(False)  # Initially hidden
        layout.addWidget(self.custom_ocio_widget)

        # Info section
        info_group = QGroupBox("Color Management Information")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel("""• ACES 1.2 (Built-in): Uses Nuke's built-in ACES configuration
    • Nuke Default: Uses Nuke's default color management, with OCIO switched to ACES 1.2 (to be able to use ACES OCIO Colorspace & Display nodes)
    • Custom OCIO: Load your own OpenColorIO configuration file

    Plate Color Space vs Working Space:
    • Plate Color Space: Colorspace of your input footage (e.g., ACEScct from camera)
    • Working Space: Internal processing colorspace (e.g., ACEScg or scene_linear)

    This allows workflows like ACEScct plates → ACEScg working space conversion.

    Note: OCIO settings only apply when generating Nuke scripts.""")
        info_text.setStyleSheet("color: #b0b0b0; font-size: 11px; line-height: 1.4;")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)

        layout.addStretch()
        return tab_widget

    def on_nuke_format_toggled(self, enabled):
        """Handle Nuke format checkbox toggle - simplified since OCIO is in separate tab"""
        # Color management is now in separate OCIO tab, so just trigger change
        if enabled:
            self.on_color_management_changed()

    def on_color_management_changed(self):
        """Handle color management type change"""
        color_text = self.nuke_color_combo.currentText()
        is_custom_ocio = "Custom OCIO" in color_text
        self.custom_ocio_widget.setVisible(is_custom_ocio)

        if is_custom_ocio and not self.ocio_path_edit.text():
            self.ocio_status_label.setText("Please select an OCIO configuration file")

    def browse_ocio_config(self):
        """Browse for OCIO configuration file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select OCIO Configuration File",
            "",
            "OCIO Config Files (*.ocio);;All Files (*)"
        )

        if file_path:
            self.ocio_path_edit.setText(file_path)
            self.parse_and_populate_ocio_settings(file_path)

    def parse_and_populate_ocio_settings(self, ocio_path):
        """Parse OCIO file and populate dropdowns"""
        self.ocio_status_label.setText("Parsing OCIO configuration...")
        QApplication.processEvents()

        parser = OCIOConfigParser()
        result = parser.parse_ocio_file(ocio_path)

        if result['success']:
            # Clear existing items
            self.plate_colorspace_combo.clear()
            self.working_space_combo.clear()
            self.display_combo.clear()
            self.view_combo.clear()
            self.viewer_process_combo.clear()

            # Populate colorspaces (both plate and working space use same list)
            colorspaces = result['colorspaces']
            self.plate_colorspace_combo.addItems(colorspaces)
            self.working_space_combo.addItems(colorspaces)

            # Set default working space
            default_ws = result['default_working_space']
            if default_ws in colorspaces:
                self.working_space_combo.setCurrentText(default_ws)

            # Set default plate colorspace (try common plate colorspaces first)
            plate_defaults = ["ACEScct", "Rec709", "sRGB", "scene_linear"]
            plate_colorspace_set = False
            for plate_default in plate_defaults:
                if plate_default in colorspaces:
                    self.plate_colorspace_combo.setCurrentText(plate_default)
                    plate_colorspace_set = True
                    break
            
            # If no common plate colorspace found, use working space as fallback
            if not plate_colorspace_set and default_ws in colorspaces:
                self.plate_colorspace_combo.setCurrentText(default_ws)

            # Populate displays
            displays = result['displays']
            self.display_combo.addItems(list(displays.keys()))

            # Populate viewer processes (combination of all display/view pairs)
            viewer_processes = []
            for display, views in displays.items():
                for view in views:
                    viewer_processes.append(f"{view} ({display})")

            # Add some common viewer processes that might not be in the OCIO
            common_processes = ["Rec.709 (ACES)", "sRGB (ACES)", "rec709", "sRGB"]
            for process in common_processes:
                if process not in viewer_processes:
                    viewer_processes.append(process)

            self.viewer_process_combo.addItems(viewer_processes)

            # Set default viewer process
            if "Rec.709 (ACES)" in viewer_processes:
                self.viewer_process_combo.setCurrentText("Rec.709 (ACES)")
            elif viewer_processes:
                self.viewer_process_combo.setCurrentText(viewer_processes[0])

            # Update displays and trigger view population
            self.on_display_changed()

            # Update status
            status_msg = f"✅ Loaded: {len(colorspaces)} colorspaces, {len(displays)} displays"
            if 'note' in result:
                status_msg += f"\n💡 {result['note']}"
            self.ocio_status_label.setText(status_msg)

        else:
            error_msg = f"❌ Error parsing OCIO file: {result.get('error', 'Unknown error')}"
            self.ocio_status_label.setText(error_msg)

            # Populate with fallback values
            self.plate_colorspace_combo.clear()
            self.plate_colorspace_combo.addItems(result['colorspaces'])
            self.working_space_combo.clear()
            self.working_space_combo.addItems(result['colorspaces'])
            self.display_combo.clear()
            self.display_combo.addItems(list(result['displays'].keys()))
            self.on_display_changed()

    def on_display_changed(self):
        """Handle display selection change - update available views"""
        if not hasattr(self, 'display_combo'):
            return

        display = self.display_combo.currentText()
        if not display:
            return

        # We need to get the displays data again or store it
        # For now, let's reparse if we have an OCIO path
        ocio_path = self.ocio_path_edit.text()
        if ocio_path:
            parser = OCIOConfigParser()
            result = parser.parse_ocio_file(ocio_path)
            if result['success'] and display in result['displays']:
                self.view_combo.clear()
                self.view_combo.addItems(result['displays'][display])
        else:
            # Fallback views
            fallback_views = ["Rec.709", "sRGB", "P3-D60"] if display == "ACES" else ["sRGB"]
            self.view_combo.clear()
            self.view_combo.addItems(fallback_views)

    def on_compression_changed(self):
        """Show/hide quality setting based on compression type and update label"""
        compression_text = self.compression_combo.currentText()

        # Map compression names to values
        compression_map = {
            "None": 0, "RLE": 1, "ZIPS": 2, "ZIP": 3,
            "PIZ": 4, "PXR24": 5, "B44": 6, "B44A": 7,
            "DWAA": 8, "DWAB": 9
        }

        compression_value = compression_map.get(compression_text, 4)  # Default to PIZ

        # Show quality only for DWAA (8) and DWAB (9)
        is_dwa_compression = compression_value in [8, 9]
        self.quality_label.setVisible(is_dwa_compression)
        self.quality_spin.setVisible(is_dwa_compression)

        # Update label text based on specific compression type
        if compression_value == 8:  # DWAA
            self.quality_label.setText("DWAA Quality:")
        elif compression_value == 9:  # DWAB
            self.quality_label.setText("DWAB Quality:")
        else:
            self.quality_label.setText("DWAA Quality:")  # Default fallback

    def create_right_panel(self):
        """Create the right output panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        # Status and controls
        controls_layout = QVBoxLayout()

        # Status
        status_label = QLabel("Status")
        status_label.setProperty("class", "section-title")
        controls_layout.addWidget(status_label)

        self.status_label = QLabel("Ready to generate comp files")
        self.status_label.setProperty("class", "status-info")
        controls_layout.addWidget(self.status_label)

        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        refresh_btn = QPushButton("Refresh Selection")
        refresh_btn.clicked.connect(self.refresh_selection)
        buttons_layout.addWidget(refresh_btn)

        generate_btn = QPushButton("Generate Files")
        generate_btn.setProperty("class", "success-button")
        generate_btn.clicked.connect(self.generate_files)
        generate_btn.setToolTip("Create Fusion and/or Nuke files with VFX Notes from selected clips")
        buttons_layout.addWidget(generate_btn)

        controls_layout.addLayout(buttons_layout)
        layout.addLayout(controls_layout)

        # Output log
        output_label = QLabel("Output Log")
        output_label.setProperty("class", "section-title")
        layout.addWidget(output_label)

        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("Generation results and VFX notes will appear here...")
        layout.addWidget(self.results_text)

        # Settings info
        settings_info = QLabel("Settings are automatically saved • Independent versioning per format")
        settings_info.setStyleSheet("color: #888; font-size: 11px; text-align: center; margin-top: 8px;")
        settings_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(settings_info)

        # Help text for VFX notes
        help_text = QLabel("💡 Add notes to: Comments or Description fields in clip properties → metadata")
        help_text.setStyleSheet("color: #666; font-size: 10px; text-align: center; margin-top: 4px;")
        help_text.setAlignment(Qt.AlignCenter)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        return panel
    
    def add_folder_structure_to_comp_tab(self, layout):
        """Add folder structure settings to comp creation tab - call this in create_comp_creation_tab"""
        
        # Add this after your EXR settings group
        folder_group = QGroupBox("Shot Folder Structure")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setSpacing(12)

        folder_desc = QLabel("Automatically create folder structure for each shot:")
        folder_desc.setStyleSheet("color: #b0b0b0; font-size: 12px; margin-bottom: 8px;")
        folder_layout.addWidget(folder_desc)

        self.create_folders_check = QCheckBox("Create shot folder structure")
        self.create_folders_check.setChecked(True)
        self.create_folders_check.setToolTip("Create additional folders based on JSON template")
        self.create_folders_check.toggled.connect(self.update_folder_preview)
        folder_layout.addWidget(self.create_folders_check)

        # Preview/configuration button
        folder_button_layout = QHBoxLayout()
        
        self.folder_preview_label = QLabel("Loading template...")
        self.folder_preview_label.setStyleSheet("color: #888; font-size: 11px;")
        folder_button_layout.addWidget(self.folder_preview_label)
        
        folder_button_layout.addStretch()
        
        configure_folders_btn = QPushButton("Configure Structure")
        configure_folders_btn.setProperty("class", "small-button")
        configure_folders_btn.setToolTip("Configure which folders are created for each shot")
        configure_folders_btn.clicked.connect(self.configure_folder_structure)
        folder_button_layout.addWidget(configure_folders_btn)
        
        folder_layout.addLayout(folder_button_layout)

        return folder_group

    # ADD these lines to your existing load_settings method:
    def add_to_load_settings(self):
        """Add these lines to your existing load_settings method"""
        create_folders = self.generator.settings_manager.get_setting("create_folder_structure")
        if hasattr(self, 'create_folders_check'):
            self.create_folders_check.setChecked(create_folders)
        self.update_folder_preview()

    # ADD these lines to your existing save_settings method:
    def add_to_save_settings(self):
        """Add these lines to your existing save_settings method"""
        if hasattr(self, 'create_folders_check'):
            self.generator.settings_manager.set_setting("create_folder_structure", self.create_folders_check.isChecked())

    def load_settings(self):
        """Load settings into GUI including render paths"""
        settings = self.generator.settings_manager

        # Load format selection
        generate_fusion = settings.get_setting("generate_fusion")
        generate_nuke = settings.get_setting("generate_nuke")
        self.fusion_check.setChecked(generate_fusion)
        self.nuke_check.setChecked(generate_nuke)

        # Load specialized format selection
        generate_fusion_depth = settings.get_setting("generate_fusion_depth")
        generate_fusion_mmask = settings.get_setting("generate_fusion_mmask")
        self.fusion_depth_check.setChecked(generate_fusion_depth)
        self.fusion_mmask_check.setChecked(generate_fusion_mmask)

        # Load Nuke color management setting
        nuke_color_mgmt = settings.get_setting("nuke_color_management")
        if nuke_color_mgmt == "nuke_default":
            self.nuke_color_combo.setCurrentText("Nuke Rec709")
        elif nuke_color_mgmt == "custom_ocio":
            self.nuke_color_combo.setCurrentText("Custom OCIO Config")
        else:  # aces_1.2 or default
            self.nuke_color_combo.setCurrentText("ACES 1.2 (Built-in)")

        # Load custom OCIO settings
        custom_ocio_config = settings.get_setting("custom_ocio_config")
        if custom_ocio_config:
            self.ocio_path_edit.setText(custom_ocio_config)
            self.parse_and_populate_ocio_settings(custom_ocio_config)

            # Set saved values
            custom_plate_colorspace = settings.get_setting("custom_ocio_plate_colorspace")
            custom_working_space = settings.get_setting("custom_ocio_working_space")
            custom_display = settings.get_setting("custom_ocio_display")
            custom_view = settings.get_setting("custom_ocio_view")
            custom_viewer_process = settings.get_setting("custom_ocio_viewer_process")

            if custom_plate_colorspace and self.plate_colorspace_combo.findText(custom_plate_colorspace) >= 0:
                self.plate_colorspace_combo.setCurrentText(custom_plate_colorspace)
            if custom_working_space and self.working_space_combo.findText(custom_working_space) >= 0:
                self.working_space_combo.setCurrentText(custom_working_space)
            if custom_display and self.display_combo.findText(custom_display) >= 0:
                self.display_combo.setCurrentText(custom_display)
                self.on_display_changed()  # Update views
            if custom_view and self.view_combo.findText(custom_view) >= 0:
                self.view_combo.setCurrentText(custom_view)
            if custom_viewer_process and self.viewer_process_combo.findText(custom_viewer_process) >= 0:
                self.viewer_process_combo.setCurrentText(custom_viewer_process)

        # Trigger color management change to show/hide custom OCIO widget
        self.on_color_management_changed()

        # Update path displays (ENHANCED for all 4 path types)
        self.current_fusion_script_label.setText(settings.get_setting("fusion_output_path"))
        self.current_nuke_script_label.setText(settings.get_setting("nuke_output_path"))
        self.current_fusion_render_label.setText(settings.get_setting("fusion_render_path"))
        self.current_nuke_render_label.setText(settings.get_setting("nuke_render_path"))

        # Load VFX Notes settings
        include_notes = settings.get_setting("include_vfx_notes")
        self.include_notes_check.setChecked(include_notes)

        notes_position = settings.get_setting("notes_position")
        position_text = "Above Loaders" if notes_position == "top" else "Right Side"
        for i in range(self.notes_position_combo.count()):
            if self.notes_position_combo.itemText(i) == position_text:
                self.notes_position_combo.setCurrentIndex(i)
                break

        # Load overwrite setting
        overwrite_existing = settings.get_setting("overwrite_existing")
        self.overwrite_check.setChecked(overwrite_existing)

        # Load scene report setting
        generate_scene_report = settings.get_setting("generate_scene_report")
        self.generate_scene_report_check.setChecked(generate_scene_report)

        # Enable/disable position combo based on checkbox
        self.notes_position_combo.setEnabled(include_notes)

        # Load EXR settings
        compression = settings.get_setting("exr_compression")
        bit_depth = settings.get_setting("exr_bit_depth")
        quality = settings.get_setting("exr_quality")

        # Map compression values to names
        compression_names = {
            0: "None", 1: "RLE", 2: "ZIPS", 3: "ZIP",
            4: "PIZ", 5: "PXR24", 6: "B44", 7: "B44A",
            8: "DWAA", 9: "DWAB"
        }

        # Set compression combo
        compression_name = compression_names.get(compression, "PIZ")
        for i in range(self.compression_combo.count()):
            if self.compression_combo.itemText(i) == compression_name:
                self.compression_combo.setCurrentIndex(i)
                break

        # Map bit depth values to names
        bit_depth_names = {1: "16-bit Float", 2: "32-bit Float"}

        # Set bit depth combo
        bit_depth_name = bit_depth_names.get(bit_depth, "16-bit Float")
        for i in range(self.bit_depth_combo.count()):
            if self.bit_depth_combo.itemText(i) == bit_depth_name:
                self.bit_depth_combo.setCurrentIndex(i)
                break

        # Set quality (only applies to DWAA/DWAB)
        self.quality_spin.setValue(quality)

        # Update quality visibility based on compression
        self.on_compression_changed()

        # Load sequence mode settings
        single_sequence_mode = settings.get_setting("single_sequence_mode")
        self.single_sequence_radio.setChecked(single_sequence_mode)
        self.versioned_sequences_radio.setChecked(not single_sequence_mode)

        # Load metadata injection settings
        metadata_injection = settings.get_setting("metadata_injection")
        self.metadata_injection_check.setChecked(metadata_injection)

        metadata_field_name = settings.get_setting("metadata_field_name")
        if metadata_field_name:
            self.metadata_field_edit.setText(metadata_field_name)

        # Load folder structure settings
        create_folders = settings.get_setting("create_folder_structure")
        if hasattr(self, 'create_folders_check'):
            self.create_folders_check.setChecked(create_folders)
        
        # Update folder preview
        if hasattr(self, 'folder_preview_label'):
            self.update_folder_preview()            

        # Load folder structure tab settings
        if hasattr(self, 'folder_structure_tab'):
            self.folder_structure_tab.load_template()

    def save_settings(self):
        """Save current GUI settings"""
        try:
            settings = self.generator.settings_manager

            # Save format selection
            settings.set_setting("generate_fusion", self.fusion_check.isChecked())
            settings.set_setting("generate_nuke", self.nuke_check.isChecked())

            # Save specialized format selection
            settings.set_setting("generate_fusion_depth", self.fusion_depth_check.isChecked())
            settings.set_setting("generate_fusion_mmask", self.fusion_mmask_check.isChecked())

            # Save Nuke color management setting
            color_text = self.nuke_color_combo.currentText()
            if "Nuke Default" in color_text or "Nuke Rec709" in color_text:
                settings.set_setting("nuke_color_management", "nuke_default")
            elif "Custom OCIO" in color_text:
                settings.set_setting("nuke_color_management", "custom_ocio")
                # Save custom OCIO settings
                settings.set_setting("custom_ocio_config", self.ocio_path_edit.text())
                settings.set_setting("custom_ocio_plate_colorspace", self.plate_colorspace_combo.currentText())
                settings.set_setting("custom_ocio_working_space", self.working_space_combo.currentText())
                settings.set_setting("custom_ocio_display", self.display_combo.currentText())
                settings.set_setting("custom_ocio_view", self.view_combo.currentText())
                settings.set_setting("custom_ocio_viewer_process", self.viewer_process_combo.currentText())
            else:  # ACES 1.2
                settings.set_setting("nuke_color_management", "aces_1.2")

            # Save VFX Notes settings
            settings.set_setting("include_vfx_notes", self.include_notes_check.isChecked())

            position_text = self.notes_position_combo.currentText()
            notes_position = "top" if position_text == "Above Loaders" else "side"
            settings.set_setting("notes_position", notes_position)

            # Save overwrite setting
            settings.set_setting("overwrite_existing", self.overwrite_check.isChecked())

            # Save scene report setting
            settings.set_setting("generate_scene_report", self.generate_scene_report_check.isChecked())

            # Save sequence mode settings
            single_sequence_mode = self.single_sequence_radio.isChecked()
            settings.set_setting("single_sequence_mode", single_sequence_mode)

            # Save metadata injection settings
            metadata_injection = self.metadata_injection_check.isChecked()
            settings.set_setting("metadata_injection", metadata_injection)

            metadata_field_name = self.metadata_field_edit.text().strip()
            if not metadata_field_name:
                metadata_field_name = "comp_version"
            settings.set_setting("metadata_field_name", metadata_field_name)

            # Save folder structure settings
            if hasattr(self, 'create_folders_check'):
                settings.set_setting("create_folder_structure", self.create_folders_check.isChecked())

            # Save EXR settings
            exr_settings = self.get_exr_settings()
            settings.set_setting("exr_compression", exr_settings['compression'])
            settings.set_setting("exr_bit_depth", exr_settings['bit_depth'])

            # Only save quality for DWAA/DWAB compression methods
            if exr_settings['compression'] in [8, 9]:
                settings.set_setting("exr_quality", exr_settings['quality'])

            # Save to file using atomic writing
            settings.save_settings()

        except Exception as e:
            print(f"ERROR in save_settings: {e}")
            import traceback
            traceback.print_exc()

    def open_settings_folder(self):
        """Open the folder containing the settings.json file"""
        try:
            import subprocess
            settings_dir = self.generator.settings_manager.settings_dir

            # Ensure the settings directory exists
            settings_dir.mkdir(parents=True, exist_ok=True)

            # Platform-specific folder opening
            system = platform.system()

            if system == "Windows":
                os.startfile(str(settings_dir))
            elif system == "Darwin":  # macOS
                subprocess.call(["open", str(settings_dir)])
            else:  # Linux and others
                subprocess.call(["xdg-open", str(settings_dir)])

            # Show brief confirmation in status
            original_text = self.status_label.text()
            original_class = self.status_label.property("class")

            self.status_label.setText(f"📁 Opened settings folder: {settings_dir}")
            self.status_label.setProperty("class", "status-info")

            # Restore original status after 3 seconds
            QTimer.singleShot(3000, lambda: (
                self.status_label.setText(original_text),
                self.status_label.setProperty("class", original_class)
            ))

        except Exception as e:
            QMessageBox.warning(self, "Error Opening Folder",
                              f"Could not open settings folder:\n{str(e)}\n\nFolder location: {self.generator.settings_manager.settings_dir}")
            print(f"Error opening settings folder: {e}")

    def edit_output_paths(self):
        """Open dialog to edit output path templates including render paths"""
        dialog = ResolvePathTemplateDialog(self, self.generator.settings_manager)

        if dialog.exec() == QDialog.Accepted:
            # Get all four path templates
            new_fusion_script = dialog.get_fusion_script_template()
            new_nuke_script = dialog.get_nuke_script_template()
            new_fusion_render = dialog.get_fusion_render_template()
            new_nuke_render = dialog.get_nuke_render_template()

            # Save to settings
            self.generator.settings_manager.set_setting("fusion_output_path", new_fusion_script)
            self.generator.settings_manager.set_setting("nuke_output_path", new_nuke_script)
            self.generator.settings_manager.set_setting("fusion_render_path", new_fusion_render)
            self.generator.settings_manager.set_setting("nuke_render_path", new_nuke_render)

            # Update display labels
            self.current_fusion_script_label.setText(new_fusion_script)
            self.current_nuke_script_label.setText(new_nuke_script)
            self.current_fusion_render_label.setText(new_fusion_render)
            self.current_nuke_render_label.setText(new_nuke_render)

            self.save_settings()

    def refresh_selection(self):
        """Refresh the selection info with VFX notes detection and format info"""
        if not self.generator.resolve:
            self.status_label.setText("DaVinci Resolve not connected")
            self.status_label.setProperty("class", "status-error")
            self.results_text.setText("Please run this script from within DaVinci Resolve")
            return

        selected_clips = self.generator.get_selected_clips()
        count = len(selected_clips)

        if count == 0:
            self.status_label.setText("No clips selected in media pool")
            self.status_label.setProperty("class", "status-info")
            self.results_text.setText("""No clips detected as selected.

    Try these steps:
    1. Select clips in the Media Pool (they should be highlighted)
    2. Click 'Refresh Selected' again
    3. If still not working, the script will process ALL clips in current folder

    Note: Some Resolve versions may not properly report clip selection.""")
        else:
            # Initialize clip_info as a list
            clip_info = []
            
            # Group clips to show shot information
            shot_groups = self.generator.group_clips_by_shot(selected_clips)
            shot_count = len(shot_groups)

            # Count VFX notes
            total_notes = 0
            if self.include_notes_check.isChecked():
                for base_name, clip_group in shot_groups.items():
                    for clip_info_item in clip_group:
                        clip_notes = self.generator.extract_vfx_notes(clip_info_item['clip'])
                        total_notes += len(clip_notes)

            # Check which formats are enabled
            formats_enabled = []
            if self.fusion_check.isChecked():
                formats_enabled.append("Fusion")
            if self.nuke_check.isChecked():
                # Add color management info
                color_text = self.nuke_color_combo.currentText()
                if "ACES" in color_text:
                    color_info = "ACES 1.2"
                elif "Custom OCIO" in color_text:
                    ocio_path = self.ocio_path_edit.text()
                    if ocio_path:
                        from pathlib import Path
                        ocio_name = Path(ocio_path).stem
                        color_info = f"OCIO ({ocio_name})"
                    else:
                        color_info = "OCIO (Not Set)"
                else:
                    color_info = "Default"
                formats_enabled.append(f"Nuke ({color_info})")
            if self.fusion_depth_check.isChecked():
                formats_enabled.append("Depth")
            if self.fusion_mmask_check.isChecked():
                formats_enabled.append("MMask")

            format_text = " + ".join(formats_enabled) if formats_enabled else "No formats selected"

            # Add sequence mode info
            single_sequence_mode = self.single_sequence_radio.isChecked()
            mode_info = "Single Seq (v999)" if single_sequence_mode else "Versioned"

            # Update status with notes count, format info, and sequence mode
            status_text = f"Found {count} clip(s) -> {shot_count} shot group(s) -> {format_text} -> {mode_info}"
            self.status_label.setText(status_text)
            self.status_label.setProperty("class", "status-success")

            for base_name, clip_group in shot_groups.items():
                # Get properties from primary clip
                primary_clip = clip_group[0]['clip']
                width, height, fps = self.generator.get_clip_properties(primary_clip)

                # List all layers in this shot
                layer_names = []
                shot_notes_count = 0

                for clip_info_item in clip_group:
                    layer_name = f"L{clip_info_item['layer_num']:02d}"
                    if clip_info_item['layer_num'] == clip_group[0]['layer_num']:
                        layer_name += " (Primary -> Output)"

                    # Count notes for this clip
                    if self.include_notes_check.isChecked():
                        clip_notes = self.generator.extract_vfx_notes(clip_info_item['clip'])
                        if clip_notes:
                            layer_name += f" [{len(clip_notes)}]"
                            shot_notes_count += len(clip_notes)

                    layer_names.append(layer_name)

                clip_info.append(f"- {base_name}")
                clip_info.append(f"  Resolution: {width}x{height} @ {fps}fps")
                clip_info.append(f"  Layers: {', '.join(layer_names)}")

                # Show VFX notes preview if enabled and available
                if self.include_notes_check.isChecked() and shot_notes_count > 0:
                    clip_info.append(f"  VFX Notes: {shot_notes_count} found")

                    # Show a preview of the first few notes
                    note_previews = []
                    for clip_info_item in clip_group[:2]:  # First 2 clips only
                        clip_notes = self.generator.extract_vfx_notes(clip_info_item['clip'])
                        for note in clip_notes[:1]:  # First note only
                            preview = note['content'][:40] + "..." if len(note['content']) > 40 else note['content']
                            note_previews.append(f"    - {note['source']}: {preview}")

                    clip_info.extend(note_previews)
                    if shot_notes_count > len(note_previews):
                        clip_info.append(f"    ... and {shot_notes_count - len(note_previews)} more")

                clip_info.append("")  # Empty line between shots

            # If debug is enabled, show properties for first clip
            if self.debug_check.isChecked() and selected_clips:
                clip_info.append("--- Debug: Available Properties (First Clip) ---")
                first_clip_properties = self.generator.collect_all_clip_properties(selected_clips[0])
                for prop, value in first_clip_properties.items():
                    clip_info.append(f"  {prop}: {value}")
                clip_info.append(f"Total properties found: {len(first_clip_properties)}")

            self.results_text.setText("\n".join(clip_info))

    def get_exr_settings(self):
        """Get EXR settings from GUI"""
        try:
            compression_text = self.compression_combo.currentText()
            bit_depth_text = self.bit_depth_combo.currentText()

            # Map compression names to values
            compression_map = {
                "None": 0, "RLE": 1, "ZIPS": 2, "ZIP": 3,
                "PIZ": 4, "PXR24": 5, "B44": 6, "B44A": 7,
                "DWAA": 8, "DWAB": 9
            }

            # Map bit depth names to values
            bit_depth_map = {"16-bit Float": 1, "32-bit Float": 2}

            compression_value = compression_map.get(compression_text, 4)  # Default to PIZ
            bit_depth_value = bit_depth_map.get(bit_depth_text, 1)       # Default to 16-bit

            # Quality only applies to DWAA/DWAB compression - get actual GUI spinner value
            quality_value = self.quality_spin.value() if compression_value in [8, 9] else 45

            return {
                'compression': compression_value,
                'bit_depth': bit_depth_value,
                'quality': quality_value
            }

        except Exception as e:
            print(f"ERROR in get_exr_settings: {e}")
            import traceback
            traceback.print_exc()
            # Return safe defaults
            return {
                'compression': 4,  # PIZ
                'bit_depth': 1,    # 16-bit Float
                'quality': 45      # Fixed default
            }

    def generate_files(self):
        """Generate files for selected clips with VFX notes and configurable color management"""
        if not self.generator.resolve:
            QMessageBox.warning(self, "Error", "DaVinci Resolve not connected")
            return

        # Check if at least one format is selected
        if not (self.fusion_check.isChecked() or self.nuke_check.isChecked() or 
                self.fusion_depth_check.isChecked() or self.fusion_mmask_check.isChecked()):
            QMessageBox.warning(self, "No Formats Selected",
                            "Please select at least one output format before generating files.")
            return

        try:
            exr_settings = self.get_exr_settings()
        except Exception as e:
            print(f"ERROR getting EXR settings: {e}")
            import traceback
            traceback.print_exc()
            return

        # CRITICAL: Save current settings BEFORE generating
        # This ensures folder creation checkbox state is persisted
        try:
            self.save_settings()
        except Exception as e:
            print(f"ERROR saving settings: {e}")
            import traceback
            traceback.print_exc()
            return

        # Show progress
        formats_generating = []
        if self.fusion_check.isChecked():
            formats_generating.append("Fusion")
        if self.nuke_check.isChecked():
            color_text = self.nuke_color_combo.currentText()
            if "ACES" in color_text:
                color_info = "ACES 1.2"
            elif "Custom OCIO" in color_text:
                ocio_path = self.ocio_path_edit.text()
                if ocio_path:
                    from pathlib import Path
                    ocio_name = Path(ocio_path).stem
                    color_info = f"OCIO ({ocio_name})"
                else:
                    color_info = "OCIO (Not Set)"
            else:
                color_info = "Default"
            formats_generating.append(f"Nuke ({color_info})")
        if self.fusion_depth_check.isChecked():
            formats_generating.append("Depth")
        if self.fusion_mmask_check.isChecked():
            formats_generating.append("MMask")

        self.status_label.setText(f"Generating {' + '.join(formats_generating)} files with VFX notes...")
        self.status_label.setProperty("class", "status-info")
        QApplication.processEvents()

        try:
            success, results = self.generator.process_selected_clips(
                exr_settings,
                self.debug_check.isChecked(),
                self.create_test_notes_check.isChecked()
            )
        except Exception as e:
            print(f"ERROR in process_selected_clips: {e}")
            import traceback
            traceback.print_exc()
            self.status_label.setText("Error during processing")
            self.status_label.setProperty("class", "status-error")
            return

        if success:
            notes_status = " with VFX Notes" if self.include_notes_check.isChecked() else ""
            format_status = " + ".join(formats_generating)
            self.status_label.setText(f"{format_status} files generated successfully{notes_status}!")
            self.status_label.setProperty("class", "status-success")
            if isinstance(results, list):
                self.results_text.setText("\n".join(results))
            else:
                self.results_text.setText(str(results))
        else:
            self.status_label.setText("Error generating files")
            self.status_label.setProperty("class", "status-error")
            self.results_text.setText(str(results))
            QMessageBox.warning(self, "Error", str(results))


def main():
    """Main entry point"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("Fusion Nuke Generator")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Pinionist")

    window = UniversalCompGUI()
    window.show()

    if app:
        try:
            app.exec()
        except AttributeError:
            app.exec_()


if __name__ == "__main__":
    main()

# Import resolve API at module level (required by DaVinci Resolve)
try:
    import DaVinciResolveScript as dvr_script
    resolve = dvr_script.scriptapp("Resolve")
except ImportError:
    print("DaVinci Resolve API not available - running in standalone mode")
    resolve = None