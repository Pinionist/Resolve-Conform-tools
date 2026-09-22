#!/usr/bin/env python3
"""
EXR Sequence Importer v1.1 - Direct Sequence Import
Finds all EXR sequences in selected path and imports them directly
"""

import os
import platform
import re
import sys
import json
from pathlib import Path
from typing import List, Dict

# DaVinci Resolve setup
def setup_resolve_paths():
    system = platform.system()
    if system == "Darwin":
        api_path = '/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so'
        lib_path = '/Applications/DaVinci Resolve/Developer/Scripting/Modules/'
    elif system == "Windows":
        possible_bases = [
            r'C:\Program Files\Blackmagic Design\DaVinci Resolve',
            r'C:\Program Files (x86)\Blackmagic Design\DaVinci Resolve',
            r'C:\Program Files\Blackmagic Design\DaVinci Resolve Studio'
        ]
        api_path = lib_path = None
        for base in possible_bases:
            test_api = os.path.join(base, 'fusionscript.dll')
            test_lib = os.path.join(base, 'Developer', 'Scripting', 'Modules')
            if os.path.exists(test_api) and os.path.exists(test_lib):
                api_path, lib_path = test_api, test_lib
                break
        if not api_path:
            api_path = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll'
            lib_path = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules'
    return api_path, lib_path

try:
    api_path, lib_path = setup_resolve_paths()
    if not os.environ.get('RESOLVE_SCRIPT_API'):
        os.environ['RESOLVE_SCRIPT_API'] = api_path
    if not os.environ.get('RESOLVE_SCRIPT_LIB'):
        os.environ['RESOLVE_SCRIPT_LIB'] = lib_path
    if lib_path not in sys.path:
        sys.path.append(lib_path)
except Exception as e:
    print(f"Environment setup warning: {e}")

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

class SettingsManager:
    def __init__(self):
        docs_path = Path.home() / "Documents" / "RendersImport"
        docs_path.mkdir(parents=True, exist_ok=True)
        
        self.settings_file = docs_path / "settings.json"
        self.default_settings = {
            "last_path": "",
            "name_filter": "comp",
            "rename_clips": True,
            "clip_color": "Violet",
            "presets": [
                {"name": "Plate v000", "filter": "plate_v000", "color": "Apricot", "rename": True},
                {"name": "Comp v999", "filter": "comp_v999", "color": "Violet", "rename": True},
                {"name": "Depth v000", "filter": "depth_v000", "color": "Green", "rename": True},
                {"name": "Custom", "filter": "", "color": "Violet", "rename": True}
            ],
            "selected_preset": 0
        }
    
    def load_settings(self) -> Dict:
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    loaded = json.load(f)
                    return {**self.default_settings, **loaded}
        except Exception as e:
            print(f"Failed to load settings: {e}")
        
        return self.default_settings.copy()
    
    def save_settings(self, settings: Dict):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")

class ResolveTheme:
    @staticmethod
    def get_main_stylesheet():
        return """
        QMainWindow { background: #525252; color: #cccccc; font-family: Arial; font-size: 13px; }
        QWidget { background: #282828; color: #cccccc; }
        QGroupBox { font-weight: 600; color: #ffffff; border: 1px solid #3a3a3a; border-radius: 6px; margin-top: 10px; padding-top: 12px; background: #2a2a2a; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; color: #cccccc; background-color: transparent; font-weight: 600; }
        QLabel { color: #cccccc; background-color: transparent; }
        .title-label { font-size: 22px; font-weight: 600; color: #4376A1; margin: 8px 0; }
        .section-title { font-size: 13px; font-weight: 600; color: #cccccc; margin-bottom: 6px; }
        .status-success { color: #0C0C0C; background: #4376A1; border: 1px solid #4376A1; border-radius: 4px; padding: 8px 16px; }
        .status-error { color: #ffffff; background: #f44336; border: 1px solid #f44336; border-radius: 4px; padding: 8px 16px; }
        .status-info { color: #0C0C0C; background: #2196F3; border: 1px solid #2196F3; border-radius: 4px; padding: 8px 16px; }
        .status-warning { color: #0C0C0C; background: #ff9800; border: 1px solid #ff9800; border-radius: 4px; padding: 8px 16px; }
        QPushButton { background: #404040; border: 1px solid #555555; border-radius: 4px; color: #cccccc; font-weight: 500; padding: 8px 16px; min-height: 16px; min-width: 80px; }
        QPushButton:hover { background: #4a4a4a; border-color: #666666; color: #ffffff; }
        .primary-button { background: #4376A1; border: 1px solid #4376A1; color: #0C0C0C; font-weight: 600; }
        .success-button { background: #4376A1; border: 1px solid #4376A1; color: #0C0C0C; font-weight: 600; }
        .small-button { padding: 6px 12px; min-height: 12px; min-width: 60px; font-size: 12px; }
        QLineEdit { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 4px; color: #cccccc; padding: 8px 12px; }
        QLineEdit:focus { border-color: #4376A1; background: #1f1f1f; }
        QCheckBox { color: #cccccc; spacing: 8px; }
        QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #3a3a3a; border-radius: 3px; background: #1a1a1a; }
        QCheckBox::indicator:checked { background: #F9423F; border-color: #F9423F; }
        QTreeWidget { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 4px; color: #cccccc; }
        QTreeWidget::item { padding: 4px; border: none; }
        QTreeWidget::item:selected { background-color: #4376A1; color: #ffffff; }
        QTreeWidget::item:hover { background-color: #333333; }
        QHeaderView::section { background: #2a2a2a; color: #cccccc; border: 1px solid #3a3a3a; padding: 6px; font-weight: 600; }
        QTextEdit { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 4px; color: #cccccc; font-family: monospace; font-size: 12px; padding: 12px; }
        QProgressBar { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 4px; text-align: center; color: #cccccc; height: 20px; }
        QProgressBar::chunk { background: #4376A1; border-radius: 3px; margin: 1px; }
        """

class EXRSequenceFinder:
    def find_all_exr_sequences(self, root_path: Path, name_filter: str = "") -> List[Dict]:
        """Find all EXR sequences recursively with optional name filtering"""
        sequences = []
        
        # Group EXR files by their base name (without frame number)
        exr_groups = {}
        
        # Find all EXR files recursively
        for exr_file in root_path.rglob("*.exr"):
            base_name, frame_num = self._extract_base_and_frame(exr_file.name)
            
            if base_name:
                # Apply name filter if specified
                if name_filter and name_filter.lower() not in base_name.lower():
                    continue
                    
                key = (exr_file.parent, base_name)
                
                if key not in exr_groups:
                    exr_groups[key] = []
                
                exr_groups[key].append({
                    'path': exr_file,
                    'frame': frame_num
                })
        
        # Convert groups to sequences
        for (folder, base_name), files in exr_groups.items():
            if len(files) > 1:  # Only sequences with multiple frames
                sorted_files = sorted(files, key=lambda x: x['frame'] if x['frame'] else 0)
                
                first_frame = sorted_files[0]['frame']
                last_frame = sorted_files[-1]['frame']
                first_file_path = sorted_files[0]['path']
                
                # Read compression type from first frame
                compression = self.get_exr_compression(first_file_path)
                
                sequences.append({
                    'folder': folder,
                    'base_name': base_name,
                    'first_file': first_file_path,
                    'last_file': sorted_files[-1]['path'],
                    'first_frame': first_frame,
                    'last_frame': last_frame,
                    'file_count': len(files),
                    'relative_path': str(folder.relative_to(root_path)),
                    'compression': compression
                })
        
        return sequences
    
    def _extract_base_and_frame(self, filename: str):
        """Extract base name and frame number from EXR filename"""
        # Pattern: name_1001.exr -> base='name', frame=1001
        match = re.match(r'(.+)_(\d{3,})\.exr$', filename, re.IGNORECASE)
        if match:
            return match.group(1), int(match.group(2))
        
        # Pattern: name.1001.exr -> base='name', frame=1001
        match = re.match(r'(.+)\.(\d{3,})\.exr$', filename, re.IGNORECASE)
        if match:
            return match.group(1), int(match.group(2))
        
        # No frame pattern found
        return Path(filename).stem, None
    
    def get_exr_compression(self, exr_path: Path) -> str:
        """Read EXR compression type from file header"""
        compression_types = {
            0: "NONE",
            1: "RLE",
            2: "ZIPS",
            3: "ZIP",
            4: "PIZ",
            5: "PXR24",
            6: "B44",
            7: "B44A",
            8: "DWAA",
            9: "DWAB"
        }
        
        try:
            with open(exr_path, 'rb') as f:
                # Read magic number
                magic = f.read(4)
                if magic != b'\x76\x2f\x31\x01':
                    return "UNKNOWN"
                
                # Read version and flags
                f.read(4)
                
                # Read header attributes
                while True:
                    # Read attribute name
                    name_bytes = b''
                    while True:
                        byte = f.read(1)
                        if byte == b'\x00' or not byte:
                            break
                        name_bytes += byte
                    
                    if not name_bytes:
                        break
                    
                    attr_name = name_bytes.decode('ascii', errors='ignore')
                    
                    # Read attribute type
                    type_bytes = b''
                    while True:
                        byte = f.read(1)
                        if byte == b'\x00' or not byte:
                            break
                        type_bytes += byte
                    
                    attr_type = type_bytes.decode('ascii', errors='ignore')
                    
                    # Read attribute size
                    size_bytes = f.read(4)
                    if len(size_bytes) < 4:
                        break
                    attr_size = int.from_bytes(size_bytes, byteorder='little')
                    
                    # Check if this is the compression attribute
                    if attr_name == "compression":
                        compression_byte = f.read(1)
                        if compression_byte:
                            comp_value = compression_byte[0]
                            return compression_types.get(comp_value, "UNKNOWN")
                    else:
                        # Skip attribute data
                        f.seek(attr_size, 1)
                
        except Exception as e:
            return "ERROR"
        
        return "UNKNOWN"

class ResolveImporter:
    def __init__(self):
        self.resolve = None
        self.project = None
        self.media_pool = None
        self.connect_to_resolve()

    def connect_to_resolve(self):
        try:
            import DaVinciResolveScript as dvr_script
            self.resolve = dvr_script.scriptapp("Resolve")
            if self.resolve:
                self.project_manager = self.resolve.GetProjectManager()
                self.project = self.project_manager.GetCurrentProject()
                if self.project:
                    self.media_pool = self.project.GetMediaPool()
                    return True
        except Exception as e:
            print(f"Failed to connect to Resolve: {e}")
        return False

    def clean_filename(self, filename):
        """Remove frame range patterns and file extensions from filename"""
        # Remove frame range patterns like _[1001-1130] or .[1001-1130]
        clean_name = re.sub(r'[._]\[\d+-\d+\]', '', filename)
        
        # Trim trailing underscores or dots before file extension
        clean_name = re.sub(r'([._]+)(\.[a-zA-Z0-9]+)$', r'\2', clean_name)
        
        # Remove file extension
        clean_name = re.sub(r'\.[a-zA-Z0-9]+$', '', clean_name)
        
        return clean_name

    def import_sequences(self, sequences: List[Dict], rename_clips: bool = True, clip_color: str = "Violet") -> List[str]:
        """Import entire comp/render folder - let Resolve handle sequence detection"""
        if not self.media_pool:
            return ["Error: Not connected to DaVinci Resolve"]

        operations = []
        
        # Get unique folders containing sequences
        unique_folders = set()
        for seq in sequences:
            folder_path = seq['folder']
            # Check if this is a comp/render path
            if 'comp' in str(folder_path).lower() or 'render' in str(folder_path).lower():
                unique_folders.add(folder_path)
        
        if not unique_folders:
            return ["No comp/render folders found in sequences"]
        
        operations.append(f"Importing {len(unique_folders)} folders containing sequences:")
        operations.append("")
        
        imported_count = 0
        failed_count = 0
        total_clips_imported = []
        
        for folder in sorted(unique_folders):
            try:
                folder_str = str(folder)
                operations.append(f"Importing folder: {folder.name}")
                
                clips = self.media_pool.ImportMedia([folder_str])
                
                if clips is not None and len(clips) > 0:
                    operations.append(f"  → Imported {len(clips)} clips")
                    total_clips_imported.extend(clips)
                    imported_count += 1
                else:
                    operations.append(f"  → Import returned nothing")
                    failed_count += 1
                    
            except Exception as e:
                operations.append(f"  → ERROR: {e}")
                failed_count += 1
        
        operations.append("")
        operations.append(f"Folders processed: {imported_count} success, {failed_count} failed")
        
        # Post-processing: rename and color clips
        if total_clips_imported:
            operations.append("")
            operations.append("Post-processing imported clips:")
            
            renamed_count = 0
            colored_count = 0
            
            for clip in total_clips_imported:
                try:
                    # Rename clip if enabled
                    if rename_clips:
                        current_name = clip.GetClipProperty("Clip Name")
                        new_name = self.clean_filename(current_name)
                        
                        if current_name != new_name:
                            success = clip.SetClipProperty("Clip Name", new_name)
                            if success:
                                renamed_count += 1
                    
                    # Set clip color
                    if clip_color:
                        success = clip.SetClipColor(clip_color)
                        if success:
                            colored_count += 1
                            
                except Exception as e:
                    operations.append(f"  → Post-process error: {e}")
            
            if rename_clips:
                operations.append(f"  → Renamed {renamed_count} clips")
            if clip_color:
                operations.append(f"  → Colored {colored_count} clips {clip_color}")
        
        return operations

    def get_media_pool_clips(self) -> Dict[str, any]:
        """Get all clips from current media pool bin with their names"""
        clips_dict = {}
        
        if not self.media_pool:
            return clips_dict
        
        try:
            root_folder = self.media_pool.GetRootFolder()
            clips_dict = self._get_clips_recursive(root_folder)
        except Exception as e:
            print(f"Error getting media pool clips: {e}")
        
        return clips_dict
    
    def _get_clips_recursive(self, folder) -> Dict[str, any]:
        """Recursively get all clips from folder and subfolders"""
        clips_dict = {}
        
        try:
            # Get clips in current folder
            clips = folder.GetClipList()
            if clips:
                for clip in clips:
                    try:
                        clip_name = clip.GetClipProperty("Clip Name")
                        if clip_name:
                            clips_dict[clip_name] = clip
                    except:
                        pass
            
            # Get clips from subfolders
            subfolders = folder.GetSubFolderList()
            if subfolders:
                for subfolder in subfolders:
                    sub_clips = self._get_clips_recursive(subfolder)
                    clips_dict.update(sub_clips)
                    
        except Exception as e:
            print(f"Error in recursive clip search: {e}")
        
        return clips_dict
    
    def check_sequence_exists(self, sequence_name: str, media_pool_clips: Dict[str, any]) -> str:
        """Check if sequence exists in media pool. Returns status string."""
        # Clean the sequence name for comparison
        clean_seq_name = self.clean_filename(sequence_name)
        
        # Check exact match
        if clean_seq_name in media_pool_clips:
            return "EXISTS"
        
        # Check if base name exists (without frame padding)
        for clip_name in media_pool_clips.keys():
            # Remove potential version numbers and check
            if clean_seq_name.lower() in clip_name.lower():
                return "EXISTS"
        
        return "NEW"

class EXRImporterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(ResolveTheme.get_main_stylesheet())
        self.finder = EXRSequenceFinder()
        self.importer = ResolveImporter()
        self.settings_manager = SettingsManager()
        self.sequences = []
        self.settings = self.settings_manager.load_settings()
        self.current_preset_index = self.settings.get("selected_preset", 0)
        self.init_ui()
        self.load_ui_from_settings()

    def init_ui(self):
        self.setWindowTitle("SequenceImporter v1.1")
        self.setGeometry(100, 100, 1200, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal layout - split left/right
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # LEFT SIDE - Controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_widget.setMaximumWidth(450)
        left_widget.setMinimumWidth(400)

        # Title
        title = QLabel("SequenceImporter")
        title.setProperty("class", "title-label")
        left_layout.addWidget(title)

        # Path Selection
        path_group = QGroupBox("Source Directory")
        path_layout = QVBoxLayout(path_group)

        path_input_layout = QHBoxLayout()
        
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select directory containing EXR sequences...")
        path_input_layout.addWidget(self.path_edit)

        browse_btn = QPushButton("Browse")
        browse_btn.setProperty("class", "small-button")
        browse_btn.clicked.connect(self.browse_directory)
        path_input_layout.addWidget(browse_btn)
        
        path_layout.addLayout(path_input_layout)

        left_layout.addWidget(path_group)

        # Preset Selection
        preset_group = QGroupBox("Import Preset")
        preset_layout = QVBoxLayout(preset_group)
        
        self.preset_combo = QComboBox()
        presets = self.settings.get("presets", self.settings_manager.default_settings["presets"])
        for preset in presets:
            self.preset_combo.addItem(preset["name"])
        self.preset_combo.setCurrentIndex(self.current_preset_index)
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        
        left_layout.addWidget(preset_group)
        
        # Filter controls
        filter_group = QGroupBox("Scan Options")
        filter_layout = QVBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("Name Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter sequences (e.g., 'comp')")
        filter_layout.addWidget(self.filter_edit)

        scan_btn = QPushButton("Scan for EXR Sequences")
        scan_btn.setProperty("class", "primary-button")
        scan_btn.clicked.connect(self.scan_sequences)
        filter_layout.addWidget(scan_btn)

        left_layout.addWidget(filter_group)

        # Post-processing options
        processing_group = QGroupBox("Post import actions")
        processing_layout = QVBoxLayout(processing_group)
        
        self.rename_checkbox = QCheckBox("Remove sequence padding")
        self.rename_checkbox.setChecked(True)
        processing_layout.addWidget(self.rename_checkbox)
        
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Clip Color:"))
        
        self.color_combo = QComboBox()
        self.color_combo.addItems([
            "Violet", "Orange", "Yellow", "Green", "Blue", 
            "Pink", "Teal", "Red", "Cyan", "Purple", 
            "Apricot", "Beige", "Navy", "Olive", "Lime", "None"
        ])
        self.color_combo.setCurrentText("Violet")
        color_layout.addWidget(self.color_combo)
        color_layout.addStretch()
        
        processing_layout.addLayout(color_layout)
        left_layout.addWidget(processing_group)

        # Connection status
        self.connection_status = QLabel("Checking Resolve connection...")
        self.connection_status.setProperty("class", "status-info")
        left_layout.addWidget(self.connection_status)

        # Import buttons
        import_buttons_layout = QHBoxLayout()
        
        import_new_btn = QPushButton("IMPORT NEW")
        import_new_btn.setProperty("class", "primary-button")
        import_new_btn.clicked.connect(self.import_new_sequences)
        import_buttons_layout.addWidget(import_new_btn)
        
        import_all_btn = QPushButton("IMPORT ALL SEQUENCES")
        import_all_btn.setProperty("class", "success-button")
        import_all_btn.clicked.connect(self.import_sequences)
        import_buttons_layout.addWidget(import_all_btn)
        
        left_layout.addLayout(import_buttons_layout)

        # Log
        log_label = QLabel("Log")
        log_label.setProperty("class", "section-title")
        left_layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setMinimumHeight(200)
        left_layout.addWidget(self.log_text)

        left_layout.addStretch()

        # RIGHT SIDE - Sequence list
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        results_label = QLabel("Found EXR Sequences")
        results_label.setProperty("class", "section-title")
        right_layout.addWidget(results_label)

        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Sequence", "Status", "Compression", "Frames", "Range", "Location"])
        right_layout.addWidget(self.results_tree)

        # Add left and right to main layout
        main_layout.addWidget(left_widget)
        main_layout.addWidget(right_widget)

        self.check_resolve_connection()

    def load_ui_from_settings(self):
        if self.settings.get("last_path"):
            self.path_edit.setText(self.settings["last_path"])
        
        # Load preset
        preset_index = self.settings.get("selected_preset", 0)
        presets = self.settings.get("presets", self.settings_manager.default_settings["presets"])
        if 0 <= preset_index < len(presets):
            preset = presets[preset_index]
            self.filter_edit.setText(preset["filter"])
            self.rename_checkbox.setChecked(preset["rename"])
            
            color_index = self.color_combo.findText(preset["color"])
            if color_index >= 0:
                self.color_combo.setCurrentIndex(color_index)

    def save_current_settings(self):
            self.settings["last_path"] = self.path_edit.text().strip()
            self.settings["selected_preset"] = self.preset_combo.currentIndex()
            
            # Update current preset values
            presets = self.settings.get("presets", self.settings_manager.default_settings["presets"])
            current_index = self.preset_combo.currentIndex()
            if 0 <= current_index < len(presets):
                presets[current_index]["filter"] = self.filter_edit.text().strip()
                presets[current_index]["rename"] = self.rename_checkbox.isChecked()
                presets[current_index]["color"] = self.color_combo.currentText()
            
            self.settings["presets"] = presets
            self.settings_manager.save_settings(self.settings)

    def on_preset_changed(self, index):
        presets = self.settings.get("presets", self.settings_manager.default_settings["presets"])
        if 0 <= index < len(presets):
            preset = presets[index]
            self.filter_edit.setText(preset["filter"])
            self.rename_checkbox.setChecked(preset["rename"])
            
            color_index = self.color_combo.findText(preset["color"])
            if color_index >= 0:
                self.color_combo.setCurrentIndex(color_index)

    def check_resolve_connection(self):
        if self.importer.connect_to_resolve():
            project_name = self.importer.project.GetName() if self.importer.project else "Unknown"
            self.connection_status.setText(f"Connected: {project_name}")
            self.connection_status.setProperty("class", "status-success")
        else:
            self.connection_status.setText("Not connected to Resolve")
            self.connection_status.setProperty("class", "status-error")

    def browse_directory(self):
        current_path = self.path_edit.text().strip()
        start_dir = current_path if current_path and os.path.exists(current_path) else ""
        
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select Directory with EXR Sequences",
            start_dir
        )
        if folder:
            self.path_edit.setText(folder)
            self.save_current_settings()

    def scan_sequences(self):
        path_text = self.path_edit.text().strip()
        if not path_text or not os.path.exists(path_text):
            self.log_text.append("Please select a valid directory")
            return

        name_filter = self.filter_edit.text().strip()

        self.results_tree.clear()
        filter_msg = f" (filtering for '{name_filter}')" if name_filter else ""
        self.log_text.append(f"Scanning for EXR sequences{filter_msg}...")
        QApplication.processEvents()

        try:
            # Get media pool clips for comparison
            media_pool_clips = self.importer.get_media_pool_clips()
            
            root_path = Path(path_text)
            self.sequences = self.finder.find_all_exr_sequences(root_path, name_filter)
            
            new_sequences = []
            existing_sequences = []
            
            # Separate sequences into new and existing
            for seq in self.sequences:
                status = self.importer.check_sequence_exists(seq['base_name'], media_pool_clips)
                seq['status'] = status
                
                if status == "NEW":
                    new_sequences.append(seq)
                else:
                    existing_sequences.append(seq)
            
            # Create parent items for sections
            if new_sequences:
                new_parent = QTreeWidgetItem([f"NEW SEQUENCES ({len(new_sequences)})", "", "", "", "", ""])
                new_parent.setBackground(0, QColor(60, 120, 60))  # Green background
                new_parent.setForeground(0, QColor(150, 255, 150))  # Green text
                
                # Bold font for parent
                parent_font = QFont()
                parent_font.setBold(True)
                parent_font.setPointSize(11)
                new_parent.setFont(0, parent_font)
                
                self.results_tree.addTopLevelItem(new_parent)
                
                for seq in new_sequences:
                    # Column order: Sequence, Status, Compression, Frames, Range, Location
                    item = QTreeWidgetItem([
                        seq['base_name'],
                        "NEW",
                        seq.get('compression', 'UNKNOWN'),
                        str(seq['file_count']),
                        f"{seq['first_frame']}-{seq['last_frame']}" if seq['first_frame'] else "N/A",
                        seq['relative_path']
                    ])
                    
                    # Bold green text for new sequences
                    bold_font = QFont()
                    bold_font.setBold(True)
                    
                    for col in range(6):
                        item.setForeground(col, QColor(150, 255, 150))
                        item.setFont(col, bold_font)
                    
                    new_parent.addChild(item)
                
                # Expand after adding all children
                new_parent.setExpanded(True)
            
            if existing_sequences:
                existing_parent = QTreeWidgetItem([f"ALREADY IMPORTED ({len(existing_sequences)})", "", "", "", "", ""])
                existing_parent.setBackground(0, QColor(60, 60, 60))  # Gray background
                existing_parent.setForeground(0, QColor(150, 150, 150))  # Gray text
                
                # Bold font for parent
                parent_font = QFont()
                parent_font.setBold(True)
                parent_font.setPointSize(11)
                existing_parent.setFont(0, parent_font)
                
                self.results_tree.addTopLevelItem(existing_parent)
                
                for seq in existing_sequences:
                    # Column order: Sequence, Status, Compression, Frames, Range, Location
                    item = QTreeWidgetItem([
                        seq['base_name'],
                        "EXISTS",
                        seq.get('compression', 'UNKNOWN'),
                        str(seq['file_count']),
                        f"{seq['first_frame']}-{seq['last_frame']}" if seq['first_frame'] else "N/A",
                        seq['relative_path']
                    ])
                    
                    # Gray text for existing sequences
                    for col in range(6):
                        item.setForeground(col, QColor(150, 150, 150))
                    
                    existing_parent.addChild(item)
                
                # Expand after adding all children
                existing_parent.setExpanded(True)

            for i in range(self.results_tree.columnCount()):
                self.results_tree.resizeColumnToContents(i)
            
            found_msg = f"Found {len(self.sequences)} EXR sequences"
            if name_filter:
                found_msg += f" containing '{name_filter}'"
            found_msg += f" ({len(new_sequences)} new, {len(existing_sequences)} already in media pool)"
            self.log_text.append(found_msg)
            
        except Exception as e:
            self.log_text.append(f"Scan error: {e}")

    def import_sequences(self):
        if not self.sequences:
            self.log_text.append("No sequences to import. Run scan first.")
            return

        if not self.importer.resolve:
            self.log_text.append("Not connected to Resolve")
            return

        try:
            self.save_current_settings()
            
            rename_clips = self.rename_checkbox.isChecked()
            clip_color = self.color_combo.currentText()
            if clip_color == "None":
                clip_color = ""
            
            operations = self.importer.import_sequences(self.sequences, rename_clips, clip_color)
            
            self.log_text.append(f"\nImporting {len(self.sequences)} sequences:")
            for operation in operations:
                self.log_text.append(operation)

        except Exception as e:
            self.log_text.append(f"Import error: {e}")

    def import_new_sequences(self):
        if not self.sequences:
            self.log_text.append("No sequences to import. Run scan first.")
            return

        if not self.importer.resolve:
            self.log_text.append("Not connected to Resolve")
            return

        try:
            # Filter only NEW sequences
            new_sequences = [seq for seq in self.sequences if seq.get('status') == 'NEW']
            
            if not new_sequences:
                self.log_text.append("No new sequences to import. All sequences already exist in media pool.")
                return
            
            self.save_current_settings()
            
            rename_clips = self.rename_checkbox.isChecked()
            clip_color = self.color_combo.currentText()
            if clip_color == "None":
                clip_color = ""
            
            operations = self.importer.import_sequences(new_sequences, rename_clips, clip_color)
            
            self.log_text.append(f"\nImporting {len(new_sequences)} NEW sequences:")
            for operation in operations:
                self.log_text.append(operation)

        except Exception as e:
            self.log_text.append(f"Import error: {e}")

def main():
    app = QApplication(sys.argv)
    window = EXRImporterGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()