import csv
import io
import os
import requests
import streamlit as st

st.set_page_config(page_title='FastHR', page_icon='📋', layout='wide')
API = os.getenv('FASTHR_API_URL', 'http://127.0.0.1:8000').rstrip('/')


def api(method, path, **kwargs):
    try:
        response = requests.request(method, API + path, timeout=(5, 180), **kwargs)
        if not response.ok:
            try:
                detail = response.json().get('detail', response.text)
            except ValueError:
                detail = response.text
            st.error(f'Не удалось выполнить действие: {detail}')
            st.stop()
        return response.json()
    except requests.RequestException:
        st.error('Backend недоступен или запрос занял слишком долго. Проверьте запуск FastHR и обновите страницу перед повторной загрузкой.')
        st.stop()


def csv_safe(value):
    text = str(value if value is not None else '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


st.title('FastHR')
st.caption('Одна вакансия → резюме → понятный рейтинг → ваш shortlist')
vacancies = api('GET', '/vacancies')
if 'new_vacancy' in st.session_state:
    st.session_state['vacancy_choice'] = st.session_state.pop('new_vacancy')
with st.sidebar:
    st.header('Вакансии')
    selected = st.selectbox('Выберите вакансию', [None] + [v['id'] for v in vacancies],
        format_func=lambda x: '＋ Новая вакансия' if x is None else next(f"{v['title']} · #{v['id']}" for v in vacancies if v['id'] == x),
        key='vacancy_choice')
    st.caption('Локальная версия 1.0 · PDF с текстовым слоем')

if selected is None:
    st.subheader('Создать вакансию')
    with st.form('create_vacancy'):
        title = st.text_input('Название', placeholder='Python Backend Developer', max_chars=200)
        description = st.text_area('Описание вакансии', height=220, placeholder='Задачи, технологии и требования к кандидату…')
        skills = st.text_input('Требуемые навыки через запятую', placeholder='Python, FastAPI, PostgreSQL, Docker, Git, AWS')
        st.caption('Укажите навыки явно: каждый имеет одинаковый вес. Без списка рейтинг будет основан на текстовом сходстве.')
        if st.form_submit_button('Создать', type='primary'):
            if not title.strip() or not description.strip():
                st.warning('Заполните название и описание.')
            else:
                created = api('POST', '/vacancies', json={'title': title, 'description': description,
                    'required_skills': [s.strip() for s in skills.split(',') if s.strip()]})
                st.session_state['new_vacancy'] = created['id']
                st.rerun()
    st.stop()

vacancy = api('GET', f'/vacancies/{selected}')
base = f'/vacancies/{selected}'
st.header(vacancy['title'])
with st.expander('Описание и требования'):
    st.write(vacancy['description'])
    st.write('Навыки: ' + (', '.join(vacancy['required_skills']) or 'Не заданы — используется текстовое сходство'))

resumes = api('GET', base + '/resumes')
a, b, c = st.columns(3)
a.metric('Загружено CV', len(resumes))
b.metric('В shortlist', sum(r['shortlisted'] for r in resumes))
c.metric('Состояние', 'Рейтинг готов' if vacancy['analyzed_at'] else 'Нужен анализ')

with st.expander('Загрузить резюме', expanded=not resumes):
    with st.form(f'upload_{selected}', clear_on_submit=True):
        uploads = st.file_uploader('PDF: до 100 за раз, до 10 МБ и 30 страниц каждый', type=['pdf'], accept_multiple_files=True)
        if st.form_submit_button('Загрузить PDF'):
            if not uploads:
                st.warning('Выберите хотя бы один PDF.')
            elif len(uploads) > 100 or any(u.size > 10 * 1024 * 1024 for u in uploads):
                st.warning('Не более 100 файлов, каждый до 10 МБ.')
            else:
                with st.spinner('Извлекаем текст и сохраняем резюме…'):
                    result = api('POST', base + '/resumes', files=[('files', (u.name, u.getvalue(), 'application/pdf')) for u in uploads])
                st.session_state[f'upload_result_{selected}'] = result
                st.rerun()
result = st.session_state.get(f'upload_result_{selected}')
if result:
    st.success(f"Последняя загрузка: принято {len(result['accepted'])}, пропущено {len(result['errors'])}.")
    for error in result['errors']:
        st.warning(f"{error['filename']}: {error['error']}")

if st.button('Рассчитать рейтинг', type='primary', disabled=not resumes):
    with st.spinner('Сравниваем все CV с вакансией…'):
        api('POST', base + '/analyze')
    st.rerun()

st.caption('Match — доля требуемых навыков, упомянутых в CV. При равенстве используется TF-IDF / cosine similarity. Это не вероятность успешного найма; упоминание навыка не подтверждает владение им.')
if not vacancy['analyzed_at']:
    st.info('Загрузите резюме и запустите анализ. После добавления новых CV нужно пересчитать весь рейтинг.')
    if resumes:
        st.dataframe([{'Файл': r['filename'], 'Имя (предположение)': r['name'] or 'Не найдено', 'Email': r['email'] or 'Не найден'} for r in resumes], hide_index=True, width='stretch')
    st.stop()

only_shortlist = st.checkbox('Показать только shortlist')
ranking = api('GET', base + '/ranking', params={'shortlisted_only': only_shortlist})
rows = [{'Место': r['rank'], 'Кандидат': r['name'] or r['filename'], 'Match %': round(r['overall_score'], 1),
         'Навыки %': round(r['skills_score'], 1) if r['skills_score'] is not None else None,
         'Текст %': round(r['cosine_score'], 1), 'Совпали': ', '.join(r['matching_skills']),
         'Не найдены': ', '.join(r['missing_skills']), 'Shortlist': r['shortlisted']} for r in ranking]
st.dataframe(rows, hide_index=True, width='stretch')
if not ranking:
    st.info('В shortlist пока никого нет.' if only_shortlist else 'Нет результатов.')
    st.stop()
export = io.StringIO()
writer = csv.writer(export)
writer.writerow(rows[0].keys())
writer.writerows([[csv_safe(v) for v in row.values()] for row in rows])
st.download_button('Скачать таблицу CSV', export.getvalue().encode('utf-8-sig'), 'fasthr-ranking.csv', 'text/csv')

st.subheader('Подробный разбор')
resume_id = st.selectbox('Выберите кандидата', [r['id'] for r in ranking],
    format_func=lambda x: next(f"#{r['rank']} · {r['name'] or r['filename']} · CV {r['id']}" for r in ranking if r['id'] == x))
detail = api('GET', base + f'/resumes/{resume_id}')
parsed, analysis = detail['parsed'], detail['analysis']
st.write(f"**Имя (предположение):** {parsed['name'] or 'Не найдено'}")
st.write(f"**Email:** {parsed['email'] or 'Не найден'} · **Телефон:** {parsed['phone'] or 'Не найден'}")
if st.button('Убрать из shortlist' if detail['shortlisted'] else 'Добавить в shortlist'):
    api('PATCH', base + f'/resumes/{resume_id}/shortlist', json={'shortlisted': not detail['shortlisted']})
    st.rerun()
if analysis:
    left, right = st.columns(2)
    left.success('Найдены: ' + (', '.join(analysis['matching_skills']) or 'Нет совпадений'))
    right.warning('Не найдены в тексте: ' + (', '.join(analysis['missing_skills']) or 'Нет'))
    with st.expander('Почему такая оценка'):
        if vacancy['required_skills']:
            st.write(f"{len(analysis['matching_skills'])} / {len(vacancy['required_skills'])} × 100 = {analysis['overall_score']:.1f}%")
        else:
            st.write('Список навыков не задан: Match равен текстовому сходству.')
        st.write(f"TF-IDF / cosine similarity: {analysis['cosine_score']:.2f}%")
        st.caption(f"Алгоритм: {analysis['algorithm']} · Запуск #{analysis['analysis_version']} · {analysis['created_at']}")
        for skill, quote in analysis['evidence'].items():
            st.write(f'**{skill}**')
            st.text(quote)
for key, label in [('experience', 'Опыт'), ('education', 'Образование'), ('projects', 'Проекты')]:
    with st.expander(label + ' — фрагмент резюме'):
        st.text(parsed['sections'].get(key) or 'Раздел автоматически не выделен. Проверьте полный текст или оригинал.')
st.write('Другие распознанные навыки: ' + (', '.join(parsed['skills']) or 'Не найдены'))
with st.expander('Полный извлечённый текст'):
    st.text(detail['text'])
st.link_button('Открыть оригинальный PDF', API + base + f'/resumes/{resume_id}/file')
