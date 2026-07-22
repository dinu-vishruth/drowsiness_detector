from app import app
from database import db, User, Session

with app.app_context():
    users = User.query.all()
    print(f'Users: {len(users)}')
    for u in users:
        print(f'  {u.username}: {len(u.sessions)} sessions')
        for s in u.sessions:
            print(f'    - Session {s.id}: duration={s.duration_seconds}s, alerts={s.alerts_count}, focus={s.focus_score}, yawns={s.yawns_count}, nods={s.nods_count}')
    
    sessions = Session.query.all()
    print(f'Total sessions in DB: {len(sessions)}')
    
    if sessions:
        s = sessions[-1]
        print(f'Latest session: duration={s.duration_seconds}s, alerts={s.alerts_count}, focus={s.focus_score}')
