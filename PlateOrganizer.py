#!/usr/bin/env python3
"""
Plate Organizer v1.7 - Enhanced with Settings & Progress
Organizes media files into proper scene/shot/asset folder structures
Added: Settings persistence, progress tracking, enhanced UX
Fixed: Scene name recognition for names with dashes/underscores
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

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


class ResolveTheme:
    """DaVinci Resolve inspired dark theme"""

    @staticmethod
    def get_main_stylesheet():
        return """
        QMainWindow { background: #525252; color: #cccccc; font-family: 'Segoe UI'; font-size: 13px; }
        QWidget { background: #282828; color: #cccccc; }
        QGroupBox { font-weight: 600; color: #ffffff; border: 1px solid #3a3a3a; border-radius: 6px; margin-top: 10px; padding-top: 12px; background: #2a2a2a; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 8px; color: #cccccc; background-color: transparent; font-weight: 600; }
        QLabel { color: #cccccc; background-color: transparent; }
        .title-label { font-size: 22px; font-weight: 600; color: #4376A1; margin: 8px 0; }
        .section-title { font-size: 13px; font-weight: 600; color: #cccccc; margin-bottom: 6px; }
        .title-label { font-size: 22px; font-weight: 600; color: #4376A1; margin: 8px 0; }
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
        QTextEdit { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 4px; color: #cccccc; font-family: monospace; font-size: 12px; padding: 12px; }
        QTableWidget { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 4px; color: #cccccc; }
        QTableWidget::item:selected { background-color: #4376A1; color: #ffffff; }
        QHeaderView::section { background: #2a2a2a; color: #cccccc; border: 1px solid #3a3a3a; padding: 6px; font-weight: 600; }
        QProgressBar { background: #1a1a1a; border: 1px solid #3a3a3a; border-radius: 4px; text-align: center; color: #cccccc; height: 20px; }
        QProgressBar::chunk { background: #4376A1; border-radius: 3px; margin: 1px; }
        """


class SettingsManager:
    """Lightweight settings management"""
    
    def __init__(self):
        self.settings_file = Path.home() / "Documents" / "PlateOrganizer" / "settings.json"
        self.settings = {"last_source_path": "", "dry_run_mode": True}
        self.load_settings()

    def load_settings(self):
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    self.settings.update(json.load(f))
        except:
            pass

    def save_settings(self):
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except:
            pass

    def get(self, key):
        return self.settings.get(key)

    def set(self, key, value):
        self.settings[key] = value


class FileOrganizer:
    """Enhanced file organization with progress tracking"""

    def extract_sequence_info_from_name(self, sequence_name: str, sequence_path: Path) -> Optional[Dict]:
        """Extract info from sequence folder name: bz_av_sh0030_L01_input_v000"""
        # Updated regex: capture everything before _sh as scene name
        match = re.search(r'^(.+)_sh(\d+)(?:_L(\d+))?_(.+?)(?:_v(\d+))?$', sequence_name, re.IGNORECASE)
        if not match:
            return None
            
        scene_name = match.group(1)  # Now captures everything before _sh
        shot_number = match.group(2)
        layer_num = int(match.group(3)) if match.group(3) else 1
        asset_name = match.group(4)
        version = match.group(5) or "000"
        shot_name = f"{scene_name}_sh{shot_number}"
        
        return {
            'scene_name': scene_name,
            'shot_name': shot_name,
            'asset_name': asset_name,
            'version': version,
            'layer': layer_num,
            'original_name': sequence_name,
            'sequence_path': sequence_path
        }

    def scan_directory(self, directory: Path, progress_callback=None) -> Dict:
        """Scan for shot+layer folders containing sequences with progress"""
        results = {'scene_groups': {}, 'unmatched_files': [], 'total_dirs': 0}

        if not directory.exists():
            return results

        folders = [f for f in directory.iterdir() if f.is_dir()]
        total_folders = len(folders)
        
        for i, folder in enumerate(folders):
            if progress_callback:
                progress_callback(i, total_folders, f"Scanning {folder.name}")
                
            results['total_dirs'] += 1
            
            # Updated regex: match everything before _sh as scene name
            shot_match = re.match(r'^(.+)_sh(\d+)(?:_L(\d+))?$', folder.name)
            if shot_match:
                scene_name = shot_match.group(1)  # Now captures everything before _sh
                shot_number = shot_match.group(2)
                base_shot_name = f"{scene_name}_sh{shot_number}"
                
                # Initialize structure
                if scene_name not in results['scene_groups']:
                    results['scene_groups'][scene_name] = {'shots': {}}
                if base_shot_name not in results['scene_groups'][scene_name]['shots']:
                    results['scene_groups'][scene_name]['shots'][base_shot_name] = {'assets': {}}
                
                # Scan sequences in this folder
                for sequence_folder in folder.iterdir():
                    if sequence_folder.is_dir():
                        sequence_info = self.extract_sequence_info_from_name(sequence_folder.name, sequence_folder)
                        if sequence_info:
                            asset_name = sequence_info['asset_name']
                            
                            if asset_name not in results['scene_groups'][scene_name]['shots'][base_shot_name]['assets']:
                                results['scene_groups'][scene_name]['shots'][base_shot_name]['assets'][asset_name] = {'sequences': []}
                            
                            file_count = sum(1 for f in sequence_folder.rglob('*') if f.is_file())
                            sequence_data = {
                                'layer': sequence_info['layer'],
                                'version': sequence_info['version'],
                                'folder_name': sequence_folder.name,
                                'path': sequence_folder,
                                'file_count': file_count,
                                'parent_folder': folder.name
                            }
                            
                            results['scene_groups'][scene_name]['shots'][base_shot_name]['assets'][asset_name]['sequences'].append(sequence_data)
            else:
                results['unmatched_files'].append({'name': folder.name, 'path': folder})

        return results

    def organize_structure(self, scene_groups: Dict, target_directory: Path, dry_run: bool = True, progress_callback=None) -> List[str]:
        """Create scene/shot/asset structure and move sequences with progress"""
        operations = []
        source_folders_to_cleanup = set()
        
        # Count total operations for progress
        total_ops = sum(
            len(shot_data['assets']) + sum(len(asset_data['sequences']) for asset_data in shot_data['assets'].values())
            for scene_data in scene_groups.values()
            for shot_data in scene_data['shots'].values()
        )
        current_op = 0

        for scene_name, scene_data in scene_groups.items():
            scene_dir = target_directory / scene_name
            if not dry_run:
                scene_dir.mkdir(exist_ok=True)
            operations.append(f"📁 Scene: {scene_dir}")

            for shot_name, shot_data in scene_data['shots'].items():
                shot_dir = scene_dir / shot_name
                if not dry_run:
                    shot_dir.mkdir(exist_ok=True)
                operations.append(f"🎬 Shot: {shot_dir}")

                for asset_name, asset_data in shot_data['assets'].items():
                    current_op += 1
                    if progress_callback:
                        progress_callback(current_op, total_ops, f"Organizing {asset_name}")
                        
                    asset_dir = shot_dir / asset_name
                    if not dry_run:
                        asset_dir.mkdir(exist_ok=True)
                    operations.append(f"🎯 Asset: {asset_dir}")

                    for sequence_data in asset_data['sequences']:
                        current_op += 1
                        if progress_callback:
                            progress_callback(current_op, total_ops, f"Moving {sequence_data['folder_name']}")
                            
                        source_path = sequence_data['path']
                        target_folder = asset_dir / source_path.name
                        source_folders_to_cleanup.add(source_path.parent)
                        
                        if dry_run:
                            operations.append(f"📄 Would move: {source_path} → {asset_dir}/")
                        else:
                            try:
                                counter = 1
                                while target_folder.exists():
                                    target_folder = asset_dir / f"{source_path.stem}_{counter}"
                                    counter += 1
                                
                                shutil.move(str(source_path), str(target_folder))
                                operations.append(f"✅ Moved: {source_path.name} → {asset_dir}/")
                            except Exception as e:
                                operations.append(f"❌ Error: {e}")

        # Cleanup empty folders
        if not dry_run:
            operations.append(f"\n🧹 Cleaning up empty folders...")
            for folder_path in source_folders_to_cleanup:
                try:
                    if folder_path.exists() and not any(folder_path.iterdir()):
                        folder_path.rmdir()
                        operations.append(f"🗑️ Deleted empty: {folder_path.name}")
                except Exception as e:
                    operations.append(f"❌ Cleanup error: {e}")
        else:
            operations.append(f"\n🧹 Would cleanup {len(source_folders_to_cleanup)} empty folders")

        return operations


class PlateOrganizerGUI(QMainWindow):
    """Enhanced Plate Organizer with settings and progress"""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(ResolveTheme.get_main_stylesheet())
        self.settings_manager = SettingsManager()
        self.file_organizer = FileOrganizer()
        self.scan_results = {}
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.setWindowTitle("Plate Organizer v1.7 - Enhanced")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(1300, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal layout like CompDeploy
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left panel - Settings and controls
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel, 1)

        # Right panel - Results and actions
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel, 1)

    def create_left_panel(self):
        """Create the left settings panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(16)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title with version
        title_layout = QHBoxLayout()
        title = QLabel("Plate Organizer")
        title.setProperty("class", "title-label")
        title_layout.addWidget(title)
        title_layout.addStretch()

        version_label = QLabel("v1.6")
        version_label.setStyleSheet("color: #888; font-size: 12px; margin-top: 4px;")
        title_layout.addWidget(version_label)
        layout.addLayout(title_layout)

        # Source Directory
        source_group = QGroupBox("Source Directory")
        source_layout = QVBoxLayout(source_group)

        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Media Folder:"))
        
        self.folder_path_edit = QLineEdit()
        self.folder_path_edit.setPlaceholderText("Select folder containing media files...")
        folder_layout.addWidget(self.folder_path_edit)

        browse_btn = QPushButton("Browse")
        browse_btn.setProperty("class", "small-button")
        browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(browse_btn)

        scan_btn = QPushButton("Scan")
        scan_btn.setProperty("class", "primary-button")
        scan_btn.clicked.connect(self.scan_folders)
        folder_layout.addWidget(scan_btn)

        source_layout.addLayout(folder_layout)

        # Enhanced info labels
        info_label = QLabel("✨ Enhanced: Settings persistence, progress tracking, detailed logging")
        info_label.setStyleSheet("color: #66bb6a; font-size: 12px; font-weight: 600;")
        source_layout.addWidget(info_label)

        tip_label = QLabel("💡 Examples: bz_av_sh0030_L01_input_v000 → bz_av/bz_av_sh0030/input/")
        tip_label.setStyleSheet("color: #4376A1; font-size: 11px;")
        source_layout.addWidget(tip_label)

        layout.addWidget(source_group)

        # Organization Settings
        org_group = QGroupBox("Organization Settings")
        org_layout = QVBoxLayout(org_group)

        self.dry_run_check = QCheckBox("Dry Run Mode (Preview Only)")
        self.dry_run_check.setChecked(True)
        org_layout.addWidget(self.dry_run_check)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        org_layout.addWidget(self.progress_bar)

        layout.addWidget(org_group)

        # Preview Table
        preview_group = QGroupBox("Structure Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.folders_table = QTableWidget()
        self.folders_table.setColumnCount(4)
        self.folders_table.setHorizontalHeaderLabels(["Scene", "Shots", "Assets", "Structure"])
        self.folders_table.horizontalHeader().setStretchLastSection(True)
        self.folders_table.setMaximumHeight(200)
        preview_layout.addWidget(self.folders_table)

        layout.addWidget(preview_group)

        layout.addStretch()
        return panel

    def create_right_panel(self):
        """Create the right results panel"""
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

        self.stats_label = QLabel("No folders scanned")
        self.stats_label.setProperty("class", "status-info")
        controls_layout.addWidget(self.stats_label)

        # Action buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        show_all_btn = QPushButton("🔍 Show All")
        show_all_btn.clicked.connect(self.show_all_folders)
        buttons_layout.addWidget(show_all_btn)

        organize_btn = QPushButton("🚀 ORGANIZE")
        organize_btn.setProperty("class", "success-button")
        organize_btn.clicked.connect(self.organize_folders)
        buttons_layout.addWidget(organize_btn)

        controls_layout.addLayout(buttons_layout)
        layout.addLayout(controls_layout)

        # Output log
        output_label = QLabel("Output Log")
        output_label.setProperty("class", "section-title")
        layout.addWidget(output_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("Organization results will appear here...")
        layout.addWidget(self.log_text)

        # Settings info
        settings_info = QLabel("Settings are automatically saved • Progress tracked during operations")
        settings_info.setStyleSheet("color: #888; font-size: 11px; text-align: center; margin-top: 8px;")
        settings_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(settings_info)

        return panel

    def load_settings(self):
        """Load saved settings"""
        last_path = self.settings_manager.get("last_source_path")
        if last_path and os.path.exists(last_path):
            self.folder_path_edit.setText(last_path)
        self.dry_run_check.setChecked(self.settings_manager.get("dry_run_mode"))

    def save_settings(self):
        """Save current settings"""
        self.settings_manager.set("last_source_path", self.folder_path_edit.text())
        self.settings_manager.set("dry_run_mode", self.dry_run_check.isChecked())
        self.settings_manager.save_settings()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Media Folder")
        if folder:
            self.folder_path_edit.setText(folder)

    def scan_folders(self):
        folder_path = self.folder_path_edit.text().strip()
        if not folder_path or not os.path.exists(folder_path):
            self.show_status("Please select a valid folder", "error")
            return

        self.log_text.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        
        def progress_callback(current, total, message):
            if total > 0:
                progress = int((current / total) * 100)
                self.progress_bar.setValue(progress)
            self.progress_bar.setFormat(f"{message}")
            QApplication.processEvents()

        try:
            self.scan_results = self.file_organizer.scan_directory(Path(folder_path), progress_callback)
            
            scene_count = len(self.scan_results['scene_groups'])
            unmatched_count = len(self.scan_results['unmatched_files'])
            
            if scene_count > 0:
                total_shots = sum(len(scene_data['shots']) for scene_data in self.scan_results['scene_groups'].values())
                total_assets = sum(
                    len(shot_data['assets'])
                    for scene_data in self.scan_results['scene_groups'].values()
                    for shot_data in scene_data['shots'].values()
                )
                
                self.stats_label.setText(f"Found {scene_count} scene(s), {total_shots} shot(s), {total_assets} asset group(s)")
                self.stats_label.setProperty("class", "status-success")
                
                self.log_text.append(f"✅ Found {scene_count} scenes with proper structure")
                
                for scene_name, scene_data in self.scan_results['scene_groups'].items():
                    self.log_text.append(f"📁 {scene_name}/")
                    for shot_name, shot_data in scene_data['shots'].items():
                        self.log_text.append(f"  🎬 {shot_name}/")
                        for asset_name in shot_data['assets'].keys():
                            folder_count = len(shot_data['assets'][asset_name]['sequences'])
                            self.log_text.append(f"    🎯 {asset_name}/ ({folder_count} folders)")
                
                if unmatched_count > 0:
                    self.log_text.append(f"⚠️ {unmatched_count} unmatched folders")
            else:
                self.stats_label.setText("No matching patterns found")
                self.stats_label.setProperty("class", "status-warning")
                self.log_text.append("❌ No scenes found - check naming patterns")

            self.populate_table()
            self.save_settings()
            
        except Exception as e:
            self.show_status(f"Scan error: {str(e)}", "error")
        finally:
            self.progress_bar.setVisible(False)

    def populate_table(self):
        scene_groups = self.scan_results.get('scene_groups', {})
        self.folders_table.setRowCount(len(scene_groups))
        
        for row, (scene_name, scene_data) in enumerate(scene_groups.items()):
            self.folders_table.setItem(row, 0, QTableWidgetItem(scene_name))
            
            shot_names = list(scene_data['shots'].keys())
            self.folders_table.setItem(row, 1, QTableWidgetItem(", ".join(shot_names)))
            
            all_assets = set()
            for shot_data in scene_data['shots'].values():
                all_assets.update(shot_data['assets'].keys())
            self.folders_table.setItem(row, 2, QTableWidgetItem(", ".join(sorted(all_assets))))
            
            if shot_names and all_assets:
                example = f"{scene_name}/{shot_names[0]}/{sorted(all_assets)[0]}/"
                self.folders_table.setItem(row, 3, QTableWidgetItem(example))

        for i in range(self.folders_table.columnCount()):
            self.folders_table.resizeColumnToContents(i)

    def show_all_folders(self):
        """Show all folders including unmatched"""
        if not self.scan_results:
            self.log_text.append("📁 No scan results. Please scan first.")
            return
            
        total_dirs = self.scan_results.get('total_dirs', 0)
        matched_count = sum(
            len(asset_data['sequences'])
            for scene_data in self.scan_results['scene_groups'].values()
            for shot_data in scene_data['shots'].values()
            for asset_data in shot_data['assets'].values()
        )
        unmatched_count = len(self.scan_results['unmatched_files'])
        
        self.log_text.append(f"📁 All Folders: {total_dirs} total, {matched_count} matched, {unmatched_count} unmatched")
        
        if unmatched_count > 0:
            self.log_text.append("Unmatched folders:")
            for item in self.scan_results['unmatched_files'][:5]:
                self.log_text.append(f"  - {item['name']}")
            if unmatched_count > 5:
                self.log_text.append(f"  ... and {unmatched_count - 5} more")

    def organize_folders(self):
        if not self.scan_results or not self.scan_results['scene_groups']:
            self.show_status("No scene groups found. Please scan first.", "warning")
            return

        source_path = Path(self.folder_path_edit.text().strip())
        dry_run = self.dry_run_check.isChecked()
        scene_count = len(self.scan_results['scene_groups'])

        mode = "DRY RUN" if dry_run else "ACTUAL ORGANIZATION"
        reply = QMessageBox.question(
            self, f"Confirm {mode}",
            f"Organize {scene_count} scene(s) in {source_path}?\n\n"
            f"Structure: scene/shot/asset/\n"
            f"Mode: {'Preview only' if dry_run else 'FILES WILL BE MOVED!'}\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        
        def progress_callback(current, total, message):
            if total > 0:
                progress = int((current / total) * 100)
                self.progress_bar.setValue(progress)
            self.progress_bar.setFormat(f"{message}")
            QApplication.processEvents()

        try:
            operations = self.file_organizer.organize_structure(
                self.scan_results['scene_groups'],
                source_path,
                dry_run,
                progress_callback
            )

            mode_prefix = "🏃‍♂️ DRY RUN" if dry_run else "🚀 ORGANIZING"
            self.log_text.append(f"\n{mode_prefix}: Starting organization...")
            
            for operation in operations:
                self.log_text.append(operation)

            if dry_run:
                self.show_status(f"Dry run complete: {scene_count} scenes previewed", "info")
            else:
                self.show_status(f"Organization complete: {scene_count} scenes organized", "success")

        except Exception as e:
            self.show_status(f"Organization error: {str(e)}", "error")
        finally:
            self.progress_bar.setVisible(False)

    def show_status(self, message, status_type="info"):
        self.stats_label.setText(message)
        self.stats_label.setProperty("class", f"status-{status_type}")
        
        icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
        self.log_text.append(f"{icons.get(status_type, 'ℹ️')} {message}")


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("Plate Organizer v1.7")
    window = PlateOrganizerGUI()
    window.show()

    if app:
        try:
            app.exec()
        except AttributeError:
            app.exec_()


if __name__ == "__main__":
    main()