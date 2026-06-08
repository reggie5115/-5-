#!/usr/bin/env python3
"""
diagnose.py  --  Open Library 연결 진단 도구

이 스크립트는 네 컴퓨터에서 Open Library가 실제로 무엇을 반환하는지 보여줘.
앱과 같은 폴더에 두고 실행해:

    python diagnose.py

네트워크가 되는지, 각 장르가 몇 권을 주는지, 어떤 정렬이 동작하는지
하나씩 출력해. 결과를 그대로 복사해서 알려주면, 거기 맞춰 코드를 조정할게.
"""

import sys
import os
import json
import time
import urllib.parse
import urllib.request

OL_BASE = "https://openlibrary.org"
UA = "BookSearchDiagnostic/1.0"


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
    elapsed = time.time() - start
    return json.loads(data), elapsed


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    print("Open Library 진단을 시작합니다...\n")

    # --- 1. 기본 연결 테스트 ------------------------------------------ #
    section("1) 인터넷 / Open Library 연결 확인")
    try:
        data, elapsed = http_get(f"{OL_BASE}/search.json?q=harry+potter&limit=1")
        n = data.get("numFound", 0)
        print(f"  성공! 응답 시간 {elapsed:.1f}초, 'harry potter' 검색 결과 {n:,}건")
    except Exception as e:
        print(f"  실패: {e}")
        print("\n  => 인터넷 연결 또는 방화벽 문제일 수 있어. "
              "회사/학교 네트워크면 프록시가 막고 있을 수 있어.")
        print("     이 메시지를 그대로 복사해서 알려줘.")
        return

    # --- 2. subjects 엔드포인트 (옛 방식) ----------------------------- #
    section("2) [옛 방식] subjects 엔드포인트가 주는 권수")
    for subj in ["fantasy", "science_fiction", "romance"]:
        try:
            data, _ = http_get(
                f"{OL_BASE}/subjects/{subj}.json?limit=100")
            works = data.get("works", [])
            total = data.get("work_count", "?")
            print(f"  {subj:18s}: 요청 100권 -> 실제 {len(works)}권 받음 "
                  f"(전체 보유 {total})")
        except Exception as e:
            print(f"  {subj:18s}: 오류 {e}")
        time.sleep(0.3)

    # --- 3. search API + 정렬 (새 방식) ------------------------------- #
    section("3) [새 방식] search API + 정렬별 권수")
    for subj in ["fantasy", "science_fiction", "romance"]:
        line = f"  {subj:18s}: "
        for sort_name, sort_val in [("관련도", None), ("평점", "rating"),
                                    ("신작", "new")]:
            params = {"q": f"subject:{subj}", "fields": "key", "limit": 100}
            if sort_val:
                params["sort"] = sort_val
            try:
                data, _ = http_get(
                    f"{OL_BASE}/search.json?{urllib.parse.urlencode(params)}")
                docs = data.get("docs", [])
                line += f"{sort_name}={len(docs)}  "
            except Exception as e:
                line += f"{sort_name}=오류  "
            time.sleep(0.3)
        print(line)

    # --- 4. 연도 필터 (현대 책) --------------------------------------- #
    section("4) [새 방식] 2000년 이후 현대 책 필터")
    for subj in ["fantasy", "thriller"]:
        params = {
            "q": f"subject:{subj} AND first_publish_year:[2000 TO 2030]",
            "fields": "key,title,first_publish_year",
            "sort": "new", "limit": 5,
        }
        try:
            data, _ = http_get(
                f"{OL_BASE}/search.json?{urllib.parse.urlencode(params)}")
            docs = data.get("docs", [])
            print(f"  {subj} (2000년 이후, 신작순) 상위 5권:")
            for d in docs:
                print(f"     - {d.get('title','?')} "
                      f"({d.get('first_publish_year','?')})")
        except Exception as e:
            print(f"  {subj}: 오류 {e}")
        time.sleep(0.3)

    # --- 5. 실제 앱 코드로 한 장르 받아보기 --------------------------- #
    section("5) 실제 앱 코드(fetch_subject)로 'fantasy' 받아보기")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from core import openlibrary as ol
        books = ol.fetch_subject("fantasy", limit=60)
        print(f"  fetch_subject('fantasy', 60) -> {len(books)}권 받음")
        if books:
            print("  샘플 5권:")
            for b in books[:5]:
                print(f"     - {b['title']} ({b.get('publish_year','?')}) "
                      f"무드:{b.get('moods')}")
    except Exception as e:
        print(f"  앱 코드 호출 오류: {e}")
        import traceback
        traceback.print_exc()

    # --- 6. 현재 저장된 DB 권수 --------------------------------------- #
    section("6) 현재 네 DB에 저장된 권수")
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "data", "library.db")
    print(f"  DB 위치: {db_path}")
    if os.path.exists(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            c = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            print(f"  현재 저장된 책: {c}권")
            # 연도 분포로 '고전 편향'인지 확인
            rows = conn.execute(
                "SELECT publish_year, COUNT(*) FROM books "
                "WHERE publish_year IS NOT NULL "
                "GROUP BY (publish_year/20)*20 ORDER BY publish_year").fetchall()
            print("  출판 연도 분포:")
            for year, cnt in rows:
                bar = "#" * min(cnt, 50)
                print(f"     {year}s: {cnt:3d}  {bar}")
        finally:
            conn.close()
    else:
        print("  아직 DB 파일이 없어 (앱을 한 번도 안 켰거나 위치가 다름).")

    print("\n" + "=" * 60)
    print("진단 끝! 위 출력 전체를 복사해서 알려줘.")
    print("=" * 60)


if __name__ == "__main__":
    main()
