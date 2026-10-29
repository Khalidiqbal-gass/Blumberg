from pathlib import Path

for path_str in [
    "src/blumberg_market_radar/models/ranking.py",
    r"C:\Users\DELL\OneDrive\Desktop\blumberg\src\blumberg_market_radar\models\ranking.py"
]:
    p = Path(path_str)
    if not p.exists():
        continue
    content = p.read_text(encoding="utf-8")
    
    # Replace lines
    old_block = """| **Lead ML Ranking Engineer** | Out-of-sample walk-forward validation & NDCG verification | `APPROVED` | {card_dict['created_date']} |
| **Quantitative Risk Officer** | Embargo buffer verification & circuit failure mode review | `APPROVED` | {card_dict['created_date']} |
| **Product Governance Lead** | Phase 6 acceptance criteria compliance check | `APPROVED` | {card_dict['created_date']} |"""
    
    new_block = """| **ML Research Module** | Out-of-sample walk-forward validation & NDCG verification | `EXPERIMENTAL - PROTOTYPE` | {card_dict['created_date']} |
| **Quantitative Engine** | Active execution engine link status | `DISCONNECTED - ENGINE USES RS_SCORE` | {card_dict['created_date']} |
| **Production Status** | Live trading & Backtest gate check | `RESEARCH SANDBOX ONLY` | {card_dict['created_date']} |"""
    
    if old_block in content:
        content = content.replace(old_block, new_block)
        p.write_text(content, encoding="utf-8")
        print(f"Updated LF: {p}")
    elif old_block.replace("\n", "\r\n") in content:
        content = content.replace(old_block.replace("\n", "\r\n"), new_block.replace("\n", "\r\n"))
        p.write_text(content, encoding="utf-8")
        print(f"Updated CRLF: {p}")
    else:
        print(f"Block not found in {p}")
