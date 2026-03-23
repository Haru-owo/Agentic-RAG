"""
Project: Enterprise Data RAG System
Module: 2-Track Auto-Tagger & Catalog Generator
Description: 
    - Office 문서 파싱 (DOCX, XLSX)
    - 임시 파일(~$ 등) 필터링
    - 공백 제거 기반 정규식 매칭
    - YY_MM_DD 날짜 패턴 정규식 추가
"""

import os
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate

# 로거 세팅
logger = logging.getLogger("AutoTagger")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s', '%H:%M:%S'))
logger.addHandler(ch)

class MetadataTagger:
    def __init__(self, model_name: str = "nemotron-3-super"):
        self.llm = OllamaLLM(model=model_name, temperature=0.0)
        
        self.llm_prompt = PromptTemplate(
            template="""[System]
당신은 문서 분류 에이전트입니다.
다음 텍스트 전체를 분석하여 문서 종류와 연도, 월을 JSON으로 반환하십시오.

[분류 기준]
- doc_type: ["일일정비일지", "정비실적보고", "주간업무보고", "MSDS", "장비이력", "정기검사", "기술매뉴얼", "일반"] 중 택 1
- year: 연도 (예: 2024) / 알 수 없으면 null
- month: 월 (예: 3) / 알 수 없으면 null

[텍스트 추출본]
{text_snippet}

[출력 형식 (오직 JSON만 출력)]
""",
            input_variables=["text_snippet"]
        )

    def extract_via_regex(self, file_path: Path, input_dir: Path) -> Dict[str, Any]:
        path_str = str(file_path).replace('\\', '/')
        rel_path = file_path.relative_to(input_dir)
        filename = file_path.name
        
        parent_dir = str(rel_path.parent).replace('\\', '/')
        if parent_dir == ".": parent_dir = "Root"
        
        metadata = {
            "filename": filename,
            "directory": parent_dir,
            "doc_type": "Unknown",
            "year": None,
            "month": None
        }
        
        # 공백 제거로 띄어쓰기 변수 차단
        path_clean = path_str.replace(" ", "")
        filename_clean = filename.replace(" ", "")
        
        # 1. 문서 타입
        if "일일정비" in path_clean or "일일보고" in path_clean:
            metadata["doc_type"] = "일일정비일지"
        elif "정비실적" in path_clean:
            metadata["doc_type"] = "정비실적보고"
        elif "주간업무" in path_clean or "주간회의록" in path_clean:
            metadata["doc_type"] = "주간업무보고"
        elif "MSDS" in path_clean.upper() or "SDS" in filename_clean.upper():
            metadata["doc_type"] = "MSDS"
        elif "CheckList" in path_clean.upper() or "교체이력" in path_clean or "트위스트락" in path_clean:
            metadata["doc_type"] = "장비이력"
        elif "정기검사" in path_clean:
            metadata["doc_type"] = "정기검사"
        elif any(kw in path_clean for kw in ["매뉴얼", "메뉴얼", "Manual", "manual", "TPS"]):
            metadata["doc_type"] = "기술매뉴얼"
        elif "발표자료" in path_clean or "TBM" in path_clean:
            metadata["doc_type"] = "일반"

        # 2. 날짜 파싱
        year_match = re.search(r'(20\d{2})년', path_clean)
        year_folder_match = re.search(r'/(20\d{2})/', path_clean)
        short_year_match = re.search(r'\'?(\d{2})년', path_clean)
        date_pattern_match = re.search(r'\(?(\d{2})(\d{2})\d{2}\)?', filename_clean)
        yy_mm_dd_match = re.search(r'(\d{2})_(\d{2})_\d{2}', filename)

        if year_match: metadata["year"] = int(year_match.group(1))
        elif year_folder_match: metadata["year"] = int(year_folder_match.group(1))
        elif date_pattern_match: metadata["year"] = int("20" + date_pattern_match.group(1))
        elif short_year_match: metadata["year"] = int("20" + short_year_match.group(1))
        elif yy_mm_dd_match: metadata["year"] = int("20" + yy_mm_dd_match.group(1))
            
        month_match = re.search(r'(\d{1,2})월', path_clean)
        if month_match: metadata["month"] = int(month_match.group(1))
        elif date_pattern_match: metadata["month"] = int(date_pattern_match.group(2))
        elif yy_mm_dd_match: metadata["month"] = int(yy_mm_dd_match.group(2))

        return metadata

    def _extract_full_text(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        snippet = ""
        
        try:
            if ext == '.docx':
                import docx
                doc = docx.Document(file_path)
                snippet = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            elif ext == '.xlsx':
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    row_data = [str(cell) for cell in row if cell is not None]
                    if row_data: snippet += " ".join(row_data) + "\n"
                wb.close() # OOM 및 File descriptor leak 방어
            elif ext in ['.txt', '.md', '.csv']:
                snippet = file_path.read_text(encoding='utf-8', errors='ignore')
            elif ext in ['.jpg', '.png', '.pptx', '.pdf']:
                snippet = f"filename: {file_path.name}"
        except Exception as e:
            logger.debug(f"파싱 실패 [{file_path.name}]: {e}")
            snippet = f"filename: {file_path.name}"
            
        return snippet

    def extract_via_llm(self, file_path: Path) -> Dict[str, Any]:
        snippet = self._extract_full_text(file_path)
        
        if len(snippet.strip()) < 10:
            return {"doc_type": "Unknown", "year": None, "month": None}
            
        try:
            response = self.llm.invoke(self.llm_prompt.format(text_snippet=snippet))
            json_str = re.search(r'\{.*\}', response, re.DOTALL)
            if json_str: return json.loads(json_str.group())
        except Exception as e:
            logger.debug(f"LLM 실패 [{file_path.name}]: {e}")
            
        return {"doc_type": "Unknown", "year": None, "month": None}

    def process_directory(self, input_dir: Path, catalog_path: Path):
        abs_dir = input_dir.resolve()
        logger.info(f"작업 시작: {abs_dir}")
        
        if not abs_dir.exists():
            logger.error("폴더 없음")
            return

        catalog = {}
        
        # Resume
        if catalog_path.exists():
            try:
                with open(catalog_path, 'r', encoding='utf-8') as f:
                    catalog = json.load(f)
                logger.info(f"기존 카탈로그 로드 ({len(catalog)}건). 이어서 진행.")
            except Exception as e:
                logger.error(f"카탈로그 로드 실패: {e}")
                catalog = {}

        target_exts = ['*.docx', '*.xlsx', '*.pptx', '*.pdf', '*.jpg', '*.png', '*.md', '*.txt']
        raw_files = []
        for ext in target_exts:
            raw_files.extend(list(input_dir.rglob(ext)))
            
        # 임시 파일 필터링
        files = [f for f in raw_files if not f.name.startswith('~$') and not f.name.startswith('.~')]
        
        total_files = len(files)
        if total_files == 0:
            logger.warning("타겟 문서 없음")
            return
            
        logger.info(f"문서 처리: 총 {total_files}건 (임시파일 제외됨)")
        success_regex = 0
        success_llm = 0
        
        start_time = time.time()
        processed_in_session = 0
        
        for idx, fpath in enumerate(files, 1):
            rel_path = str(fpath.relative_to(input_dir)).replace('\\', '/')
            
            # 스킵
            if rel_path in catalog:
                continue

            meta = self.extract_via_regex(fpath, input_dir)
            
            if meta["doc_type"] == "Unknown" or meta["year"] is None:
                llm_meta = self.extract_via_llm(fpath)
                
                # 덮어쓰기 로직 수정 (정규식 결과가 우선, 없으면 LLM 결과 사용)
                if llm_meta.get("doc_type") and llm_meta.get("doc_type") != "Unknown":
                    meta["doc_type"] = llm_meta["doc_type"]
                meta["year"] = meta.get("year") or llm_meta.get("year")
                meta["month"] = meta.get("month") or llm_meta.get("month")
                success_llm += 1
            else:
                success_regex += 1
                
            catalog[rel_path] = meta
            processed_in_session += 1
            
            # Auto-save
            with open(catalog_path, 'w', encoding='utf-8') as f:
                json.dump(catalog, f, ensure_ascii=False, indent=4)
            
            # ETA 산출
            elapsed = time.time() - start_time
            avg_time = elapsed / processed_in_session
            eta_sec = (total_files - idx) * avg_time
            eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_sec))
            pct = (idx / total_files) * 100
            
            logger.info(f"[{idx}/{total_files}] {pct:.1f}% | 소요: {elapsed:.1f}s | 남은시간: {eta_str} | 파일: {fpath.name}")
            
        logger.info(f"분류 완료. (Regex: {success_regex}, LLM: {success_llm})")

if __name__ == "__main__":
    INPUT_DIR = Path("./data") 
    CATALOG_PATH = Path("./file_catalog.json")
    
    tagger = MetadataTagger(model_name="nemotron-3-super")
    tagger.process_directory(INPUT_DIR, CATALOG_PATH)