# 아르카온 1차 검증 — 실행 전 템플릿

arkaon-first-manifest.json은 실행 결과가 아닌 UNEXECUTED_TEMPLATE입니다. 이 파일을 추가한 것으로 검증·감사가 완료되지 않습니다.

기존 ../manifest.json·../browser-manifest.json·PNG는 덮어쓰지 않습니다. 실행 시 이 템플릿을 고유 run별 하위 폴더에 복사하고 실제 SHA·명령·환경·결과·화면 검토 메모와 새 증거 해시를 채웁니다. 현재 템플릿은 NOT_RUN으로 보존합니다. 원 artifact 96개 해시 대조와 별도 재현 실행의 새 manifest/파일 내부 해시 대조를 구분하세요. 새 PNG가 원 PNG와 같은 해시여야 한다고 요구하지 않습니다.

실제 실행 후 record_kind를 EXECUTION_RESULT로 바꾸고 검증 결과를 PASS 또는 FAIL로 기록합니다. 실행되지 않은 항목은 NOT_RUN, 환경 차단은 BLOCKED로 남깁니다. 원본 해시 검증·24행/12조건·undo/redo·저장 복원·화면 표본 검토 중 미완이 있으면 전체 PASS로 표시하지 않습니다. 기준선 4건 FAIL은 비교 관찰 결과로 보존하며 후보 FAIL과 혼동하지 않습니다.

최소 필수: 실제 run ID 또는 로컬 실행 식별자·tested_head·시간·환경·명령·새 manifest와 SHA-256·원 artifact 대조 결과·화면별 검토자/시각/관찰·남은 위험·롤백. 주장한 contributor 문자열이나 digest만으로 검증 주체가 인증되지는 않습니다.

에테르니언 구현자가 만든 기존 증거를 이름만 바꿔 아르카온 검증으로 제출하지 않습니다. 독립 감사·전체 시각 검토·개선 인정·병합·운영반영 승인은 별개이며 이 템플릿으로 승인하지 않습니다. 재현 명령과 원 artifact는 PR #123의 1차 검증 지시 및 docs/86을 따릅니다.
