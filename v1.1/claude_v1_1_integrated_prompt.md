# Claude v1.1 开发提示词（已整合真实上游调用地址）

你将基于已有 v1.0 Python PySide6 桌面应用继续开发 v1.1。

请严格遵循 `diandian_mini_desktop_v1_1_spec_integrated.md`。

重点注意：

1. 本项目是单机桌面应用，不要改成 Web 后端。
2. 不要引入 FastAPI / Flask / Redis / Celery。
3. 保持 v1.0 数据库兼容。
4. 按规格书第 19 节顺序开发。
5. 按第 21 节实现真实上游调用地址：
   - Google Play 优先使用 `google-play-scraper`
   - App Store 可用 `itunes.apple.com/search`、`lookup`、RSS，或 Node `app-store-scraper`
   - OpenAI 使用 `https://api.openai.com/v1/responses`
   - Ollama 使用 `http://localhost:11434/api/chat`
6. 所有耗时操作不能阻塞 UI。
7. 所有新增功能都要有中文 UI 文案。
8. 商业化相关不能声称真实收入。
9. 完成后更新 README，并补充测试。
