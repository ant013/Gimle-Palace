# Исправление bootstrap fullAudit: рабочий каталог builder

## Контекст и допущения

Первичный bootstrap `fullaudit` на iMac создал компанию и восемь агентов, но на шаге
сборки prompt-ов остановился с `missing project manifest`. Скрипт был запущен по
абсолютному пути из домашнего каталога оператора; `build.sh` передаёт текущий каталог
как корень репозитория в Python builder. Предполагается, что bootstrap должен быть
независим от каталога, из которого его вызвали.

## Объём

- Перед вызовом project builder закрепить текущий каталог на вычисленном `REPO_ROOT`.
- Добавить регрессионную проверку, запускающую bootstrap-путь из чужого cwd на
изолированном fixture/stub уровне.
- Повторно выполнить bootstrap `fullaudit`, который обязан переиспользовать созданные
company/agent bindings и развернуть инструкции.

## Не входит

- Изменение ролей fullAudit, состава агентов, sandbox-политики или источника секретов.
- Удаление уже созданных Paperclip ресурсов.

## Затрагиваемые области

- `paperclips/scripts/bootstrap-project.sh`
- `paperclips/tests/test_fullaudit_assembly.py` или узкий bootstrap-тест

## Критерии приёмки

1. `bootstrap-project.sh` собирает prompt-ы корректно при вызове из произвольного cwd.
2. Существующие legacy-проекты сохраняют поведение.
3. Повторный bootstrap `fullaudit` завершается успешно, prompt-ы доставлены всем восьми
   агентам, quick smoke проходит.

## Проверка

- `bash -n paperclips/scripts/bootstrap-project.sh`;
- существующие и новый узкий тесты bootstrap;
- CI PR;
- на iMac: idempotent bootstrap и `smoke-test.sh fullaudit --quick`.

## Открытые вопросы

Нет: причина подтверждена живым bootstrap-логом, исправление ограничено одним cwd.
