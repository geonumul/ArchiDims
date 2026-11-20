# ArchiDims · 건축 치수 사전

스케치업에서 인체치수, 법정 최소·최대 치수, 설계 권장 치수를 검색하는 루비 확장입니다.

## 설치

1. `dist/arch_dims.rbz`를 내려받습니다.
2. 스케치업 `확장 프로그램 > Extension Manager > Install Extension`에서 설치합니다.
3. `확장 프로그램 > 건축 치수 사전` 또는 툴바 버튼으로 엽니다.

법정 항목을 누르면 법령 원문이 함께 나옵니다. 원문은 이 저장소의 `law_snapshot.json`을 하루 한 번 자동으로 내려받아 보여 줍니다. 인증키는 필요 없습니다.

## 법령 스냅샷 갱신 (관리자용)

법제처 OPEN API는 신청할 때 등록한 IP에서만 응답합니다. 그래서 등록된 PC에서 스냅샷을 만들어 이 저장소에 올립니다.

처음 한 번:

```
git clone https://github.com/geonumul/ArchiDims.git
cd ArchiDims
python tools\update_snapshot.py --push
```

- 인증키(OC)를 물어보면 입력합니다. 입력한 키는 `tools/config.local.json`에 저장되고 저장소에는 올라가지 않습니다.
- 이때 GitHub 로그인 창이 뜨면 로그인합니다. 이후에는 자동으로 푸시됩니다.

자동 실행 등록:

- `tools\register_task.bat`를 더블클릭합니다.
- 매주 월요일 10시에 실행되고, 그 시간에 PC가 꺼져 있었으면 다음에 켤 때 실행됩니다.
- 법령이 바뀐 경우에만 커밋합니다. 실행 기록은 `tools/update.log`에 남습니다.

## 새 버전 배포 (관리자용)

1. `plugin/` 안의 파일을 고칩니다.
2. `plugin/kg_arch_dims.rb`의 `VERSION`과 `version.json`의 `version`을 같은 값으로 올립니다.
3. `plugin` 폴더 안의 `kg_arch_dims.rb`와 `kg_arch_dims` 폴더를 zip으로 묶어 `dist/arch_dims.rbz`로 저장합니다.
4. 커밋하고 푸시합니다.

설치한 사람은 처음 열 때 자동 업데이트 여부를 고릅니다. 자동을 고른 사람은 매주 한 번 확인해서 자동 설치되고, 직접을 고른 사람은 창 위쪽에 업데이트 버튼이 뜹니다.

## 구성

| 경로 | 내용 |
|---|---|
| `plugin/` | 확장 소스 (`data.json`이 치수 데이터) |
| `dist/arch_dims.rbz` | 설치 파일 |
| `tools/update_snapshot.py` | 법령 스냅샷 생성·푸시 |
| `law_snapshot.json` | 배포되는 법령 스냅샷 (자동 생성) |

## 주의

- 수치는 설계 참고용입니다. 실제 도면과 인허가에는 국가법령정보센터 최신 원문을 확인하세요.
- 권장값과 인체치수는 법령이 아니라 관행·인간공학 자료 기반 근사값입니다.
