from bs4 import BeautifulSoup
from typing import Optional, List


class HTMLNode:
    def __init__(
        self,
        bs: BeautifulSoup,
        original_html: Optional[str] = None,
        original_tag_path: Optional[str] = None,
    ) -> None:
        self.bs = bs
        self.information: Optional[str] = None
        self.child_node: List['HTMLNode'] = []
        self.tag = None
        self.original_html: Optional[str] = original_html
        self.original_tag_path: Optional[str] = original_tag_path

    def append_node(self, node: 'HTMLNode') -> None:
        """子节点增加"""
        self.child_node.append(node)

    def update_information(self, information: str) -> None:
        """更新本节点信息"""
        self.information = information

    def print_information(self, depth: int = 0) -> None:
        """递归打印节点信息，带缩进显示层级关系"""
        indent = "  " * depth  # 每层多缩进2个空格

        if self.information is not None:
            print(f"{indent}{self.information}")
        else:
            print(f"{indent}[No information]")

        # 递归打印子节点
        for child in self.child_node:
            child.print_information(depth + 1)

    def child_node_count(self) -> int:
        """返回子节点数量"""
        return len(self.child_node)
