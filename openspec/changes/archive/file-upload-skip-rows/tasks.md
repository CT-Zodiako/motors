# Tasks — file-upload-skip-rows

- [x] Backend: skip_rows in extract_csv/extract_xlsx (TDD: 5 unit tests)
- [x] Backend: skipRows form field on inspect(csv)/preview/load (TDD: 4 endpoint tests + 2 load tests)
- [x] Frontend service: optional skipRows on inspect/preview/load (TDD: 3 specs)
- [x] Frontend wizard: startRow signal, inputs on source+sheet steps, retry button, cache key includes skip (TDD: 3 specs)
- [x] Verify: backend 164 passed, frontend 46 passed, ng build OK
- [x] Live verify: original file, dirty sheet, skipRows=2 → preview 200 (46 rows, real headers)
- [x] Sync: Configurable Start Row → file-upload canonical; Wizard Start-Row Input → file-upload-ui canonical
