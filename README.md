# 표준국어대사전 MCP — Claude Desktop Extension (.dxt)

## 설치

1. **국립국어원 Open API 키**를 발급받으세요.  
    https://stdict.korean.go.kr/openapi/openApiRegister.do (회원 가입 필요)
2. 컴퓨터에 [uv를 설치](https://docs.astral.sh/uv/getting-started/installation/)합니다.
3. 이 저장소의 [releases](https://github.com/ychoi-kr/ko-stdict-mcp-server/releases)에서 `.dxt` 파일을 다운로드합니다.
4. 받은 `.dxt` 파일(`ko-stdict-mcp-server-1.0.0-uv.dxt`)을 더블 클릭하거나 Claude Desktop에 드래그 앤드 드롭해서 설치합니다.
5. 설치 중 API Key 입력 창이 뜨면 발급받은 키를 입력합니다. 값은 OS Keychain에 안전 저장됩니다.

## 사용 방법

* Claude 대화에서 "표준국어대사전에서 ○○ 찾아줘"와 같이 요청하면 MCP 서버의 `search` / `entry` 도구가 자동 호출됩니다.
* 항목의 Markdown 리소스는 `stdict://entry/{target_code}` 형식으로 열 수 있습니다.  
  예: `stdict://entry/404765`

## 주의 사항

* API 호출은 국립국어원 쿼터 제한이 있으므로 과도한 호출을 피하세요.
* 오류 메시지가 뜨면 안내된 코드와 설명을 확인하고, 필요 시 API 키나 쿼리 파라미터를 점검하세요.
