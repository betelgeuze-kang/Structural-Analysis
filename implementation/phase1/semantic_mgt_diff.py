"""
Phase IV-3: 의미론적 MGT diff 생성기

기존의 단순 line-by-line diff 대신 MIDAS MGT 포맷의 의미론적 블록(ELEMENT, SECTION, LOAD 등)
단위로 변경사항을 구조화하여 비교하는 모듈입니다.

Usage:
    from semantic_mgt_diff import SemanticMgtDiff
    differ = SemanticMgtDiff(original_mgt_text, optimized_mgt_text)
    diff_report = differ.generate_report()
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MgtBlock:
    name: str  # e.g., "*ELEMENT", "*SECTION"
    headers: list[str] = field(default_factory=list)
    records: dict[str, str] = field(default_factory=dict)  # id -> content string


class SemanticMgtDiff:
    """MIDAS MGT 파일의 의미론적 블록 단위 diff 생성기."""

    def __init__(self, original_text: str, optimized_text: str):
        self.original_text = original_text
        self.optimized_text = optimized_text

    def _parse_blocks(self, text: str) -> dict[str, MgtBlock]:
        blocks: dict[str, MgtBlock] = {}
        current_block: MgtBlock | None = None
        
        for line in text.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith(";"):
                continue
                
            if line_s.startswith("*"):
                # New block
                block_name = line_s.split()[0].upper()
                current_block = MgtBlock(name=block_name)
                blocks[block_name] = current_block
                continue
                
            if current_block is None:
                continue
                
            # Parse record
            # Usually records start with integer ID, e.g. "1, COLUMN, ..."
            match = re.match(r"^(\d+)\s*,", line_s)
            if match:
                record_id = match.group(1)
                current_block.records[record_id] = line_s
            elif line_s.startswith(";") or line_s.startswith("!"):
                # Headers or comments inside block
                current_block.headers.append(line_s)
            else:
                # Some blocks might not use numeric keys at start, use whole line as key or index
                key = line_s.split(",")[0].strip() if "," in line_s else line_s
                current_block.records[key] = line_s
                
        return blocks

    def generate_report(self) -> dict[str, Any]:
        """두 MGT 데이터를 비교하여 추가/삭제/변경 항목을 의미론적으로 분석합니다."""
        orig_blocks = self._parse_blocks(self.original_text)
        opt_blocks = self._parse_blocks(self.optimized_text)
        
        report: dict[str, Any] = {
            "summary": {
                "blocks_changed": 0,
                "items_added": 0,
                "items_removed": 0,
                "items_modified": 0
            },
            "changes": {}
        }
        
        all_block_names = set(orig_blocks.keys()) | set(opt_blocks.keys())
        
        for b_name in sorted(all_block_names):
            orig_b = orig_blocks.get(b_name, MgtBlock(name=b_name))
            opt_b = opt_blocks.get(b_name, MgtBlock(name=b_name))
            
            orig_keys = set(orig_b.records.keys())
            opt_keys = set(opt_b.records.records.keys() if hasattr(opt_b.records, 'keys') else opt_b.records.keys())
            
            added = opt_keys - orig_keys
            removed = orig_keys - opt_keys
            common = orig_keys & opt_keys
            
            modified = []
            for key in common:
                if orig_b.records[key] != opt_b.records[key]:
                    modified.append({
                        "id": key,
                        "from": orig_b.records[key],
                        "to": opt_b.records[key]
                    })
                    
            if added or removed or modified:
                report["summary"]["blocks_changed"] += 1
                report["summary"]["items_added"] += len(added)
                report["summary"]["items_removed"] += len(removed)
                report["summary"]["items_modified"] += len(modified)
                
                report["changes"][b_name] = {
                    "added": {k: opt_b.records[k] for k in added},
                    "removed": {k: orig_b.records[k] for k in removed},
                    "modified": modified
                }
                
        return report

    def generate_diff_text(self) -> str:
        """인간이 읽기 쉬운 형태의 의미론적 diff 텍스트를 반환합니다."""
        report = self.generate_report()
        lines = []
        lines.append("=== Semantic MGT Diff Report ===")
        lines.append(f"Blocks Changed:   {report['summary']['blocks_changed']}")
        lines.append(f"Items Added:      {report['summary']['items_added']}")
        lines.append(f"Items Removed:    {report['summary']['items_removed']}")
        lines.append(f"Items Modified:   {report['summary']['items_modified']}")
        lines.append("================================\n")
        
        for b_name, changes in report["changes"].items():
            lines.append(f"[{b_name}]")
            for k, v in changes["added"].items():
                lines.append(f"  + Added [{k}]: {v}")
            for k, v in changes["removed"].items():
                lines.append(f"  - Removed [{k}]: {v}")
            for mod in changes["modified"]:
                lines.append(f"  ~ Modified [{mod['id']}]")
                lines.append(f"    - {mod['from']}")
                lines.append(f"    + {mod['to']}")
            lines.append("")
            
        return "\n".join(lines)


if __name__ == "__main__":
    # Test example
    mgt_old = "*ELEMENT\n1, COLUMN, 1, 2\n2, BEAM, 2, 3\n*SECTION\n101, H400\n102, H200"
    mgt_new = "*ELEMENT\n1, COLUMN, 1, 2, 101\n2, BEAM, 2, 3\n3, BRACE, 1, 3\n*SECTION\n101, H450\n102, H200"
    
    differ = SemanticMgtDiff(mgt_old, mgt_new)
    print(differ.generate_diff_text())
