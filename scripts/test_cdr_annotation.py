
import json
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path，以便能导入 pipeline 模块
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from pipeline.cdr import annotate_cdrs
from unittest.mock import patch

def test_cdr_annotation():
    # 设置输入文件路径 (使用测试数据)
    input_pdb = Path("tests/data/hotspot_sample.pdb")
    output_dir = Path("debug_cdr_output")
    
    print(f"正在处理文件: {input_pdb}")
    
    # Mock _extract_sequence to return a valid VHH sequence
    # This allows us to test the logic even if the PDB file is dummy
    valid_vhh_sequence = (
        "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMHWVRQAPGKGLEWVSAISWNSGSTYYADSVKGRFTISRDNAKNTL"
        "YLQMNSLRAEDTAVYYCARRRGVFDYWGQGTLVTVSS"
    )
    
    with patch("pipeline.cdr._extract_sequence", return_value=valid_vhh_sequence):
        # 调用核心函数
        # 注意：这里假设 PDB 中有一个重链 (H chain) 或者我们让它自动检测
        result = annotate_cdrs(
            structure_path=input_pdb,
            output_dir=output_dir,
            scheme="chothia",  # 支持 chothia, imgt 等
            chain_type="H"     # 指定链类型
        )
    
    # 打印结果摘要
    print("\n--- 运行结果 ---")
    print(f"状态: {result.get('status')}")
    
    if result.get('status') == 'succeeded':
        print(f"CDR 数量: {len(result.get('cdrs', []))}")
        print("CDR 详情:")
        for cdr in result.get('cdrs', []):
            print(f"  - {cdr['name']}: {cdr['sequence']} (Length: {cdr['length']})")
            
        print(f"\n详细结果已保存到: {output_dir}")
        print(f"JSON: {output_dir / 'cdr_annotations.json'}")
        print(f"CSV: {output_dir / 'cdr_annotations.csv'}")
    else:
        print(f"失败原因: {result.get('reason')}")

if __name__ == "__main__":
    test_cdr_annotation()
