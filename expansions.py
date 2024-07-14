import sys
import os
from datetime import datetime
from typing import Tuple, Dict, Any
import json
import requests
import anthropic
import re

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, QTextEdit,
    QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QInputDialog, QLabel
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

client = anthropic.Anthropic(
    api_key = os.environ.get("ANTHROPIC_API_KEY")
)

class ExpansionEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_item = None
        self.tree = None
        self.text_edit = None
        self.rubric_tooltip = self.extract_rubric_from_prompt()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Expansion Editor')
        self.setGeometry(100, 100, 1000, 600)

        main_widget = QWidget()
        main_layout = QHBoxLayout()

        self.create_tree_widget()
        self.create_text_edit()
        button_layout = self.create_button_layout()

        main_layout.addWidget(self.tree)
        main_layout.addWidget(self.text_edit)
        main_layout.addLayout(button_layout)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        self.load_or_create_file('outline.txt')

    def load_or_create_file(self, filename: str):
        if not os.path.exists(filename):
            self.create_default_outline(filename)
        self.load_file(filename)

    def create_default_outline(self, filename: str):
        default_content = """[LEVEL 1]My Story
[LEVEL 2]Chapter 1
[LEVEL 3]Scene 1
Write your first scene here.
[/LEVEL 3]
[LEVEL 3]Scene 2
Write your second scene here.
[/LEVEL 3]
[/LEVEL 2]
[LEVEL 2]Chapter 2
[LEVEL 3]Scene 1
Continue your story here.
[/LEVEL 3]
[/LEVEL 2]
[/LEVEL 1]"""
        
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(default_content)
        print(f"Created default outline file: {filename}")

    def extract_rubric_from_prompt(self) -> str:
        prompt = self.create_evaluation_prompt("")
        rubric_pattern = r"Evaluate the following scene based on these criteria:(.*?)For each criterion, provide a score from 1 to 5, where:"
        criteria_pattern = r"(\d+)\.\s+(.*?)(?=\n\d+\.|\n\n|$)"
        score_pattern = r"(\d+)\s*=\s*(.*?)\s*\((.*?)\)"

        rubric_match = re.search(rubric_pattern, prompt, re.DOTALL)
        if rubric_match:
            criteria_text = rubric_match.group(1).strip()
            criteria = re.findall(criteria_pattern, criteria_text, re.DOTALL)
            
            scores_text = re.search(r"For each criterion, provide a score from 1 to 5, where:(.*?)Scene content:", prompt, re.DOTALL)
            if scores_text:
                scores = re.findall(score_pattern, scores_text.group(1))
                
                tooltip = "<b>Evaluation Rubric:</b><br><br>"
                for number, criterion in criteria:
                    tooltip += f"{number}. <b>{criterion.strip()}</b><br>"
                tooltip += "<br><b>Scoring:</b><br>"
                for score, description, color in scores:
                    tooltip += f"{score} = {description} ({color})<br>"
                
                return tooltip
        
        return "Rubric information not found in the prompt."

    def create_tree_widget(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel('Outline')
        self.tree.itemClicked.connect(self.item_clicked)
        
        tree_font = self.tree.font()
        tree_font.setPointSize(14)
        self.tree.setFont(tree_font)

    def create_text_edit(self):
        self.text_edit = QTextEdit()
        
        text_font = self.text_edit.font()
        text_font.setPointSize(14)
        self.text_edit.setFont(text_font)

    def create_button_layout(self):
        button_layout = QVBoxLayout()
        buttons = [
            ('Add Node', self.add_node),
            ('Save', self.save_file),
            ('Move Up', self.move_node_up),
            ('Move Down', self.move_node_down),
            ('Promote', self.promote_node),
            ('Demote', self.demote_node),
            ('Evaluate Scene', self.evaluate_scene),
            ('Evaluate All', self.evaluate_all_scenes),
            ('Clear All Evaluations', self.clear_all_evaluations)
        ]

        for button_text, button_function in buttons:
            button = QPushButton(button_text)
            button.clicked.connect(button_function)
            button_layout.addWidget(button)

        rubric_label = QLabel("Rubric")
        rubric_label.setToolTip(self.rubric_tooltip)
        button_layout.addWidget(rubric_label)

        button_layout.addStretch(1)
        return button_layout

    def clear_all_evaluations(self):
        root = self.tree.invisibleRootItem()
        self.clear_evaluations_recursive(root)
        self.save_file()
        print("All evaluations have been cleared.")

    def clear_evaluations_recursive(self, item: QTreeWidgetItem):
        item.setData(0, Qt.UserRole + 2, None)
        
        widget = item.treeWidget().itemWidget(item, 0)
        if widget:
            layout = widget.layout()
            while layout.count() > 2:
                widget = layout.takeAt(2).widget()
                if widget:
                    widget.deleteLater()

        for i in range(item.childCount()):
            self.clear_evaluations_recursive(item.child(i))

    def load_file(self, filename: str):
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()

        self.tree.clear()
        stack = [self.tree.invisibleRootItem()]
        current_level = 0
        current_content = ""
        current_evaluation = None

        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('[LEVEL') and ']' in line:
                if current_content:
                    stack[-1].setData(0, Qt.UserRole + 1, current_content.strip())
                    if current_evaluation:
                        stack[-1].setData(0, Qt.UserRole + 2, current_evaluation)
                        self.update_scene_evaluation_display(stack[-1], current_evaluation)
                    current_content = ""
                    current_evaluation = None
                self.process_level_line(line, stack, current_level)
            elif line.startswith('[/LEVEL'):
                if current_content:
                    stack[-1].setData(0, Qt.UserRole + 1, current_content.strip())
                    if current_evaluation:
                        stack[-1].setData(0, Qt.UserRole + 2, current_evaluation)
                        self.update_scene_evaluation_display(stack[-1], current_evaluation)
                    current_content = ""
                    current_evaluation = None
                stack.pop()
                current_level -= 1
            elif line.startswith('[EVALUATION]'):
                current_evaluation = json.loads(line[12:])
            else:
                current_content += line + "\n"

        if current_content and stack:
            stack[-1].setData(0, Qt.UserRole + 1, current_content.strip())
            if current_evaluation:
                stack[-1].setData(0, Qt.UserRole + 2, current_evaluation)
                self.update_scene_evaluation_display(stack[-1], current_evaluation)

        self.tree.expandAll()

    def process_level_line(self, line: str, stack: list, current_level: int):
        try:
            level = int(line[6:line.index(']')])
            title = line[line.index(']')+1:].strip()
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.UserRole, (line, f"[/LEVEL {level}]"))
            
            while current_level >= level:
                stack.pop()
                current_level -= 1
            
            stack[-1].addChild(item)
            stack.append(item)
            current_level = level
        except ValueError:
            print(f"Skipping invalid line: {line}")

    def item_clicked(self, item: QTreeWidgetItem, column: int):
        if self.current_item:
            self.save_current_item_content()
        self.current_item = item
        content = item.data(0, Qt.UserRole + 1) or ""
        self.text_edit.setText(content)

    def save_current_item_content(self):
        if self.current_item:
            content = self.text_edit.toPlainText()
            self.current_item.setData(0, Qt.UserRole + 1, content)

    def add_node(self):
        current_item = self.tree.currentItem()
        if current_item is None:
            level = 1
            parent = self.tree.invisibleRootItem()
        else:
            start_tag, _ = current_item.data(0, Qt.UserRole)
            parent_level = int(start_tag[6:start_tag.index(']')])
            level = parent_level + 1
            parent = current_item

        title, ok = QInputDialog.getText(self, 'Add Node', 'Enter node title:')
        if ok and title:
            new_item = QTreeWidgetItem([title])
            start_tag = f"[LEVEL {level}]{title}"
            end_tag = f"[/LEVEL {level}]"
            new_item.setData(0, Qt.UserRole, (start_tag, end_tag))
            parent.addChild(new_item)
            self.tree.expandItem(parent)
            
            self.save_file_structure()

    def save_file(self):
        self.save_current_item_content()
        content = self.generate_content(self.tree.invisibleRootItem())
        self.save_to_file('outline.txt', content)
        self.create_timestamped_copy(content)

    def save_to_file(self, filename: str, content: str):
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Saved to: {filename}")

    def create_timestamped_copy(self, content: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"outline_{timestamp}.txt"
        self.save_to_file(filename, content)

    def generate_content(self, parent_item: QTreeWidgetItem) -> str:
        content = ""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            start_tag, end_tag = child.data(0, Qt.UserRole)
            content += f"{start_tag}\n"
            
            item_content = child.data(0, Qt.UserRole + 1) or ""
            content += f"{item_content}\n"
            
            evaluation_data = child.data(0, Qt.UserRole + 2)
            if evaluation_data:
                content += f"[EVALUATION]{json.dumps(evaluation_data)}\n"
            
            child_content = self.generate_content(child)
            if child_content:
                content += child_content
            
            content += f"{end_tag}\n"
        return content

    def save_file_structure(self):
        content = self.generate_content(self.tree.invisibleRootItem())
        with open('outline.txt', 'w', encoding='utf-8') as file:
            file.write(content)

    def move_node_up(self):
        current_item = self.tree.currentItem()
        if current_item:
            self.move_node(current_item, -1)

    def move_node_down(self):
        current_item = self.tree.currentItem()
        if current_item:
            self.move_node(current_item, 1)

    def move_node(self, item: QTreeWidgetItem, direction: int):
        parent = item.parent() or self.tree.invisibleRootItem()
        index = parent.indexOfChild(item)
        if 0 <= index + direction < parent.childCount():
            parent.takeChild(index)
            parent.insertChild(index + direction, item)
            self.tree.setCurrentItem(item)
            self.save_file_structure()

    def promote_node(self):
        current_item = self.tree.currentItem()
        if current_item:
            parent = current_item.parent()
            if parent and parent.parent():
                grand_parent = parent.parent()
                index = parent.indexOfChild(current_item)
                parent.takeChild(index)
                grand_parent_index = grand_parent.indexOfChild(parent)
                grand_parent.insertChild(grand_parent_index + 1, current_item)
                self.update_node_level(current_item, -1)
                self.tree.setCurrentItem(current_item)
                self.save_file_structure()

    def demote_node(self):
        current_item = self.tree.currentItem()
        if current_item:
            parent = current_item.parent() or self.tree.invisibleRootItem()
            index = parent.indexOfChild(current_item)
            if index > 0:
                sibling = parent.child(index - 1)
                parent.takeChild(index)
                sibling.addChild(current_item)
                self.update_node_level(current_item, 1)
                self.tree.setCurrentItem(current_item)
                self.save_file_structure()

    def update_node_level(self, item: QTreeWidgetItem, level_change: int):
        start_tag, end_tag = item.data(0, Qt.UserRole)
        current_level = int(start_tag[6:start_tag.index(']')])
        new_level = current_level + level_change
        new_start_tag = f"[LEVEL {new_level}]{item.text(0)}"
        new_end_tag = f"[/LEVEL {new_level}]"
        item.setData(0, Qt.UserRole, (new_start_tag, new_end_tag))

        for i in range(item.childCount()):
            self.update_node_level(item.child(i), level_change)

    def evaluate_scene(self):
        current_item = self.tree.currentItem()
        if current_item:
            start_tag, _ = current_item.data(0, Qt.UserRole)
            level = int(start_tag[6:start_tag.index(']')])
            if level == 5 or level == 6:
                scene_content = current_item.data(0, Qt.UserRole + 1) or ""
                if len(scene_content) >= 500:
                    print(f"Evaluating scene: {current_item.text(0)}")
                    evaluation = self.get_scene_evaluation(scene_content)
                    if "error" in evaluation:
                        print(f"Evaluation error: {evaluation['error']['comment']}")
                    else:
                        try:
                            self.update_scene_evaluation_display(current_item, evaluation)
                            print(f"Evaluation completed for {current_item.text(0)}")
                        except Exception as e:
                            print(f"Error updating scene evaluation display: {str(e)}")
                            print(f"Evaluation data: {evaluation}")
                else:
                    print(f"Skipping scene {current_item.text(0)} (less than 500 characters)")
            else:
                print(f"Level is {level}, please select a level 5 or 6 item (scene) to evaluate.")
        else:
            print("No item selected")

    def evaluate_all_scenes(self):
        print("Starting evaluation of all scenes...")
        root = self.tree.invisibleRootItem()
        self.evaluate_tree_items(root)
        print("Evaluation of all scenes completed.")

    def evaluate_tree_items(self, parent_item: QTreeWidgetItem):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            start_tag, _ = child.data(0, Qt.UserRole)
            level = int(start_tag[6:start_tag.index(']')])
            
            if level == 5 or level == 6:
                scene_content = child.data(0, Qt.UserRole + 1) or ""
                if len(scene_content) >= 500:
                    print(f"Evaluating scene: {child.text(0)}")
                    evaluation = self.get_scene_evaluation(scene_content)
                    if "error" in evaluation:
                        print(f"Evaluation error for {child.text(0)}: {evaluation['error']['comment']}")
                    else:
                        try:
                            self.update_scene_evaluation_display(child, evaluation)
                            print(f"Evaluation completed for {child.text(0)}")
                        except Exception as e:
                            print(f"Error updating scene evaluation display for {child.text(0)}: {str(e)}")
                            print(f"Evaluation data: {evaluation}")
                else:
                    print(f"Skipping scene {child.text(0)} (less than 500 characters)")
            
            self.evaluate_tree_items(child)

    def get_scene_evaluation(self, scene_content: str) -> Dict[str, Any]:
        prompt = self.create_evaluation_prompt(scene_content)
        
        message = client.messages.create(
            model="claude-instant-1.2",
            max_tokens=1000,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        
        if isinstance(message.content, list) and len(message.content) > 0 and hasattr(message.content[0], 'text'):
            response_text = message.content[0].text
        else:
            response_text = str(message.content)

        try:
            evaluation = json.loads(response_text)
            return evaluation
        except json.JSONDecodeError:
            return {
                "error": {
                    "score": 0,
                    "comment": "Failed to parse evaluation response"
                }
            }

    def update_scene_evaluation_display(self, item: QTreeWidgetItem, evaluation: Dict[str, Any]):
        if evaluation:
            for criterion, data in evaluation.items():
                score = data['score']
                comment = data['comment']
                color = self.get_color_for_score(score)
                self.add_evaluation_pip(item, criterion, color, comment)
            item.setData(0, Qt.UserRole + 2, evaluation)  # Store evaluation data

    def create_evaluation_prompt(self, scene_content: str) -> str:
        return f"""
        Evaluate the following scene based on these criteria:
        1. Dialogue
        2. Hooks and Transitions
        3. Theme/Subtext
        4. Prose Quality
        5. Relevance to Overall Story

        For each criterion, provide a score from 1 to 5, where:
        1 = Poor (Red)
        2 = Fair (Orange)
        3 = Good (Yellow)
        4 = Very Good (Light Green)
        5 = Excellent (Dark Green)

        Scene content:
        {scene_content}

        Provide your evaluation as a JSON object with the following structure:
        {{
            "Dialogue": {{
                "score": <int>,
                "comment": <string>
            }},
            "Hooks_and_Transitions": {{
                "score": <int>,
                "comment": <string>
            }},
            "Theme_Subtext": {{
                "score": <int>,
                "comment": <string>
            }},
            "Prose_Quality": {{
                "score": <int>,
                "comment": <string>
            }},
            "Relevance_to_Overall_Story": {{
                "score": <int>,
                "comment": <string>
            }}
        }}
        """

    def get_color_for_score(self, score: int) -> QColor:
        colors = {
            1: QColor(255, 0, 0),    # Red
            2: QColor(255, 165, 0),  # Orange
            3: QColor(255, 255, 0),  # Yellow
            4: QColor(144, 238, 144),  # Light Green
            5: QColor(0, 128, 0)     # Dark Green
        }
        return colors.get(score, QColor(0, 0, 0))  # Default to black if score is invalid

    def add_evaluation_pip(self, item: QTreeWidgetItem, criterion: str, color: QColor, comment: str):
        pip = QLabel()
        pip.setFixedSize(10, 10)
        pip.setStyleSheet(f"background-color: {color.name()}; border-radius: 5px;")
        pip.setToolTip(f"{criterion}: {comment}")

        layout = self.get_or_create_item_layout(item)
        layout.addWidget(pip)

        # Add rubric tooltip to the layout
        if layout.count() == 2:  # Only add the tooltip label once
            tooltip_label = QLabel("?")
            tooltip_label.setToolTip(self.rubric_tooltip)
            layout.addWidget(tooltip_label)

    def get_or_create_item_layout(self, item: QTreeWidgetItem) -> QHBoxLayout:
        widget = item.treeWidget().itemWidget(item, 0)
        if not widget:
            widget = QWidget()
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(QLabel(item.text(0)))
            layout.addStretch()
            widget.setLayout(layout)
            item.treeWidget().setItemWidget(item, 0, widget)
        else:
            layout = widget.layout()

        return layout

def main():
    app = QApplication(sys.argv)
    editor = ExpansionEditor()
    editor.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()