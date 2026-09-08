import os
import csv
from io import StringIO
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, abort, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, extract

app = Flask(__name__)
app.config.from_object('config.Config')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para acessar esta página.'

# ==================== MODELOS ====================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(500), default='default.png')
    bio = db.Column(db.Text, nullable=True)
    weight_kg = db.Column(db.Float, nullable=True)
    height_cm = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    runs = db.relationship('Run', backref='user', lazy=True, cascade='all, delete-orphan')
    goals = db.relationship('Goal', backref='user', lazy=True, cascade='all, delete-orphan')
    badges = db.relationship('UserBadge', backref='user', lazy=True, cascade='all, delete-orphan')
    likes_given = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='user', lazy=True, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', foreign_keys='Notification.user_id', backref='notified_user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_total_distance(self):
        return db.session.query(func.coalesce(func.sum(Run.distance_km), 0)).filter(Run.user_id == self.id).scalar()

    def get_total_runs(self):
        return Run.query.filter_by(user_id=self.id).count()

    def get_total_duration(self):
        return db.session.query(func.coalesce(func.sum(Run.duration_minutes), 0)).filter(Run.user_id == self.id).scalar()

    def get_avg_pace(self):
        total_dist = self.get_total_distance()
        total_time = self.get_total_duration()
        if total_dist > 0:
            return total_time / total_dist
        return 0

    def get_avg_speed(self):
        total_dist = self.get_total_distance()
        total_time = self.get_total_duration()
        if total_time > 0:
            return total_dist / (total_time / 60)
        return 0

    def get_calories_burned(self):
        if not self.weight_kg:
            return 0
        total_dist = self.get_total_distance()
        return total_dist * self.weight_kg * 0.75

    def is_following(self, user_id):
        return Follower.query.filter_by(follower_id=self.id, followed_id=user_id).first() is not None

    def get_followers_count(self):
        return Follower.query.filter_by(followed_id=self.id).count()

    def get_following_count(self):
        return Follower.query.filter_by(follower_id=self.id).count()

    def get_unread_notifications_count(self):
        return Notification.query.filter_by(user_id=self.id, read=False).count()

    def get_personal_records(self):
        records = {}
        max_run = Run.query.filter_by(user_id=self.id).order_by(Run.distance_km.desc()).first()
        if max_run:
            records['max_distance'] = max_run.distance_km
        
        fastest_run = Run.query.filter_by(user_id=self.id).filter(Run.distance_km >= 1).order_by(Run.duration_minutes / Run.distance_km).first()
        if fastest_run:
            records['fastest_pace'] = fastest_run.pace
            records['fastest_run_distance'] = fastest_run.distance_km
        
        for dist in [5, 10, 21, 42]:
            best = Run.query.filter_by(user_id=self.id).filter(Run.distance_km >= dist).order_by(Run.duration_minutes / Run.distance_km).first()
            if best:
                records[f'best_{dist}km'] = best.pace
        
        return records

    def get_current_streak(self):
        runs = Run.query.filter_by(user_id=self.id).order_by(Run.date.desc()).all()
        if not runs:
            return 0
        
        streak = 0
        current_date = datetime.utcnow().date()
        run_dates = set(r.date.date() for r in runs)
        
        if current_date not in run_dates:
            current_date -= timedelta(days=1)
        
        while current_date in run_dates:
            streak += 1
            current_date -= timedelta(days=1)
        
        return streak


class Run(db.Model):
    __tablename__ = 'runs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    duration_minutes = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    route_name = db.Column(db.String(120), nullable=True)
    calories = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    likes = db.relationship('Like', backref='run', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='run', lazy=True, cascade='all, delete-orphan')

    @property
    def pace(self):
        if self.distance_km > 0:
            return self.duration_minutes / self.distance_km
        return 0

    @property
    def speed(self):
        if self.duration_minutes > 0:
            return self.distance_km / (self.duration_minutes / 60)
        return 0

    def calculate_calories(self, user_weight):
        if user_weight:
            self.calories = self.distance_km * user_weight * 0.75
        else:
            self.calories = None

    def get_likes_count(self):
        return Like.query.filter_by(run_id=self.id).count()

    def get_comments_count(self):
        return Comment.query.filter_by(run_id=self.id).count()


class Goal(db.Model):
    __tablename__ = 'goals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    goal_type = db.Column(db.String(30), nullable=False)
    target_value = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)
    achieved = db.Column(db.Boolean, default=False)


class Badge(db.Model):
    __tablename__ = 'badges'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(50), nullable=False)
    condition_type = db.Column(db.String(30), nullable=False)
    threshold = db.Column(db.Float, nullable=False)


class UserBadge(db.Model):
    __tablename__ = 'user_badges'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badges.id'), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    badge = db.relationship('Badge', backref='user_badges')


class Follower(db.Model):
    __tablename__ = 'followers'
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    follower = db.relationship('User', foreign_keys=[follower_id], backref='following_relationships')
    followed = db.relationship('User', foreign_keys=[followed_id], backref='follower_relationships')


class Like(db.Model):
    __tablename__ = 'likes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    run_id = db.Column(db.Integer, db.ForeignKey('runs.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    run_id = db.Column(db.Integer, db.ForeignKey('runs.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notification_type = db.Column(db.String(30), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_notifications')


# ==================== FUNÇÕES AUXILIARES ====================

def seed_badges():
    badges = [
        Badge(name='Primeiro Passo', description='Registre sua primeira corrida', icon='bi-flag', condition_type='total_runs', threshold=1),
        Badge(name='5 km de uma vez', description='Complete uma corrida de 5 km ou mais', icon='bi-trophy', condition_type='single_run_distance', threshold=5),
        Badge(name='10 km de uma vez', description='Complete uma corrida de 10 km ou mais', icon='bi-award', condition_type='single_run_distance', threshold=10),
        Badge(name='Meia Maratona', description='Complete uma corrida de 21 km ou mais', icon='bi-gem', condition_type='single_run_distance', threshold=21),
        Badge(name='Maratonista', description='Complete uma corrida de 42 km ou mais', icon='bi-star', condition_type='single_run_distance', threshold=42),
        Badge(name='50 km acumulados', description='Acumule 50 km de corrida', icon='bi-stars', condition_type='total_distance', threshold=50),
        Badge(name='100 km acumulados', description='Acumule 100 km de corrida', icon='bi-trophy-fill', condition_type='total_distance', threshold=100),
        Badge(name='500 km acumulados', description='Acumule 500 km de corrida', icon='bi-award-fill', condition_type='total_distance', threshold=500),
        Badge(name='10 corridas', description='Complete 10 corridas', icon='bi-calendar-check', condition_type='total_runs', threshold=10),
        Badge(name='50 corridas', description='Complete 50 corridas', icon='bi-calendar-heart', condition_type='total_runs', threshold=50),
        Badge(name='Ritmo rápido', description='Corrida com ritmo menor que 5 min/km', icon='bi-lightning', condition_type='single_run_pace', threshold=5),
    ]
    for badge in badges:
        db.session.add(badge)
    db.session.commit()


def check_and_award_badges(user):
    total_distance = user.get_total_distance()
    total_runs = user.get_total_runs()
    
    last_run = Run.query.filter_by(user_id=user.id).order_by(Run.date.desc()).first()
    last_run_distance = last_run.distance_km if last_run else 0
    last_run_pace = last_run.pace if last_run else 999
    
    existing_badge_ids = [ub.badge_id for ub in UserBadge.query.filter_by(user_id=user.id).all()]
    all_badges = Badge.query.all()
    
    for badge in all_badges:
        if badge.id in existing_badge_ids:
            continue
            
        condition_met = False
        if badge.condition_type == 'total_distance':
            condition_met = total_distance >= badge.threshold
        elif badge.condition_type == 'total_runs':
            condition_met = total_runs >= badge.threshold
        elif badge.condition_type == 'single_run_distance':
            condition_met = last_run_distance >= badge.threshold
        elif badge.condition_type == 'single_run_pace':
            condition_met = last_run_pace <= badge.threshold and last_run_pace > 0

        if condition_met:
            user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(user_badge)
            flash(f'🏅 Você ganhou a medalha "{badge.name}"!', 'success')
    
    db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==================== ROTAS DE AUTENTICAÇÃO ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if not username or not email or not password:
            flash('Todos os campos são obrigatórios.', 'danger')
        elif password != confirm:
            flash('As senhas não coincidem.', 'danger')
        elif len(password) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Nome de usuário já existe.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'danger')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Conta criada com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash('Login realizado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        
        flash('Usuário ou senha inválidos.', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))


# ==================== ROTAS DO DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    runs = Run.query.filter_by(user_id=current_user.id).order_by(Run.date.desc()).all()

    total_distance = sum(r.distance_km for r in runs)
    total_duration = sum(r.duration_minutes for r in runs)
    total_runs = len(runs)
    avg_pace = total_duration / total_distance if total_distance > 0 else 0
    avg_speed = total_distance / (total_duration / 60) if total_duration > 0 else 0
    calories = current_user.get_calories_burned()

    monthly_data = db.session.query(
        extract('year', Run.date).label('year'),
        extract('month', Run.date).label('month'),
        func.sum(Run.distance_km).label('total_distance')
    ).filter(Run.user_id == current_user.id).group_by('year', 'month').order_by('year', 'month').all()

    months_labels = [f"{int(m[1]):02d}/{int(m[0])}" for m in monthly_data]
    monthly_distances = [float(m[2]) for m in monthly_data]

    recent_runs = Run.query.filter_by(user_id=current_user.id).order_by(Run.date.desc()).limit(10).all()
    pace_labels = [r.date.strftime('%d/%m') for r in reversed(recent_runs)]
    pace_data = [r.pace for r in reversed(recent_runs)]

    active_goals = Goal.query.filter_by(user_id=current_user.id, achieved=False).all()
    recent_badges = UserBadge.query.filter_by(user_id=current_user.id).order_by(UserBadge.awarded_at.desc()).limit(5).all()

    return render_template('dashboard.html',
                           total_distance=total_distance,
                           total_duration=total_duration,
                           total_runs=total_runs,
                           avg_pace=avg_pace,
                           avg_speed=avg_speed,
                           calories=calories,
                           runs=runs[:5],
                           months_labels=months_labels,
                           monthly_distances=monthly_distances,
                           pace_labels=pace_labels,
                           pace_data=pace_data,
                           active_goals=active_goals,
                           recent_badges=recent_badges)


# ==================== ROTAS DE CORRIDAS ====================

@app.route('/add_run', methods=['GET', 'POST'])
@login_required
def add_run():
    if request.method == 'POST':
        try:
            distance = float(request.form.get('distance', 0))
            hours = int(request.form.get('hours', 0) or 0)
            minutes = int(request.form.get('minutes', 0) or 0)
            seconds = int(request.form.get('seconds', 0) or 0)
            duration = hours * 60 + minutes + seconds / 60
            date_str = request.form.get('date', '')
            notes = request.form.get('notes', '')
            route_name = request.form.get('route_name', '')

            if distance <= 0 or duration <= 0:
                flash('Distância e duração devem ser maiores que zero.', 'danger')
            else:
                run_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.utcnow()
                run = Run(user_id=current_user.id, distance_km=distance, duration_minutes=duration, date=run_date, notes=notes, route_name=route_name)
                run.calculate_calories(current_user.weight_kg)
                db.session.add(run)
                db.session.commit()
                check_and_award_badges(current_user)
                flash('Corrida registrada com sucesso!', 'success')
                return redirect(url_for('dashboard'))
        except ValueError:
            flash('Dados inválidos. Verifique os campos.', 'danger')
    
    return render_template('add_run.html', today=datetime.utcnow().strftime('%Y-%m-%d'))


@app.route('/edit_run/<int:run_id>', methods=['GET', 'POST'])
@login_required
def edit_run(run_id):
    run = Run.query.get_or_404(run_id)
    if run.user_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        try:
            distance = float(request.form.get('distance', run.distance_km))
            hours = int(request.form.get('hours', int(run.duration_minutes // 60)))
            minutes = int(request.form.get('minutes', int(run.duration_minutes % 60)))
            seconds = int(request.form.get('seconds', int((run.duration_minutes * 60) % 60)))
            duration = hours * 60 + minutes + seconds / 60
            date_str = request.form.get('date', run.date.strftime('%Y-%m-%d'))
            notes = request.form.get('notes', run.notes or '')
            route_name = request.form.get('route_name', run.route_name or '')

            if distance <= 0 or duration <= 0:
                flash('Distância e duração devem ser maiores que zero.', 'danger')
            else:
                run.distance_km = distance
                run.duration_minutes = duration
                run.date = datetime.strptime(date_str, '%Y-%m-%d')
                run.notes = notes
                run.route_name = route_name
                run.calculate_calories(current_user.weight_kg)
                db.session.commit()
                check_and_award_badges(current_user)
                flash('Corrida atualizada!', 'success')
                return redirect(url_for('run_detail', run_id=run.id))
        except ValueError:
            flash('Dados inválidos. Verifique os campos.', 'danger')

    hours = int(run.duration_minutes // 60)
    minutes = int(run.duration_minutes % 60)
    seconds = int((run.duration_minutes * 60) % 60)
    return render_template('edit_run.html', run=run, hours=hours, minutes=minutes, seconds=seconds)


@app.route('/run/<int:run_id>')
@login_required
def run_detail(run_id):
    run = Run.query.get_or_404(run_id)
    return render_template('run_detail.html', run=run)


@app.route('/delete_run/<int:run_id>', methods=['POST'])
@login_required
def delete_run(run_id):
    run = Run.query.get_or_404(run_id)
    if run.user_id != current_user.id:
        abort(403)
    db.session.delete(run)
    db.session.commit()
    flash('Corrida excluída.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/runs')
@login_required
def list_runs():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    min_distance = request.args.get('min_distance', type=float)

    query = Run.query.filter_by(user_id=current_user.id)

    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Run.date >= d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d')
            query = query.filter(Run.date <= d_to)
        except ValueError:
            pass
    if min_distance:
        query = query.filter(Run.distance_km >= min_distance)

    query = query.order_by(Run.date.desc())
    runs_paginated = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('list_runs.html', runs=runs_paginated.items, pagination=runs_paginated, date_from=date_from, date_to=date_to, min_distance=min_distance)


# ==================== ROTAS DE PERFIL ====================

@app.route('/profile')
@login_required
def profile():
    return redirect(url_for('public_profile', username=current_user.username))


@app.route('/user/<username>')
@login_required
def public_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    total_distance = user.get_total_distance()
    total_runs = user.get_total_runs()
    total_duration = user.get_total_duration()
    avg_pace = user.get_avg_pace()
    avg_speed = user.get_avg_speed()
    calories = user.get_calories_burned()
    
    recent_runs = Run.query.filter_by(user_id=user.id).order_by(Run.date.desc()).limit(10).all()
    user_badges = UserBadge.query.filter_by(user_id=user.id).order_by(UserBadge.awarded_at.desc()).all()
    active_goals = Goal.query.filter_by(user_id=user.id, achieved=False).all()
    
    is_own_profile = current_user.id == user.id
    is_following = current_user.is_following(user.id) if not is_own_profile else False
    
    followers_count = user.get_followers_count()
    following_count = user.get_following_count()
    
    return render_template('public_profile.html',
                           user=user,
                           total_distance=total_distance,
                           total_runs=total_runs,
                           total_duration=total_duration,
                           avg_pace=avg_pace,
                           avg_speed=avg_speed,
                           calories=calories,
                           recent_runs=recent_runs,
                           user_badges=user_badges,
                           active_goals=active_goals,
                           is_own_profile=is_own_profile,
                           is_following=is_following,
                           followers_count=followers_count,
                           following_count=following_count)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            email = request.form.get('email', '').strip()
            bio = request.form.get('bio', '')
            weight = request.form.get('weight', type=float)
            height = request.form.get('height', type=float)

            if not email:
                flash('E-mail não pode ser vazio.', 'danger')
            elif email != current_user.email and User.query.filter_by(email=email).first():
                flash('E-mail já está em uso.', 'danger')
            else:
                current_user.email = email
                current_user.bio = bio
                current_user.weight_kg = weight
                current_user.height_cm = height
                
                avatar = request.form.get('avatar', '')
                if avatar:
                    current_user.avatar = avatar
                
                db.session.commit()
                flash('Perfil atualizado com sucesso!', 'success')
        
        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if not current_user.check_password(current_password):
                flash('Senha atual incorreta.', 'danger')
            elif new_password != confirm_password:
                flash('Nova senha e confirmação não coincidem.', 'danger')
            elif len(new_password) < 6:
                flash('A nova senha deve ter pelo menos 6 caracteres.', 'danger')
            else:
                current_user.set_password(new_password)
                db.session.commit()
                flash('Senha alterada com sucesso!', 'success')
        
        return redirect(url_for('settings'))
    
    return render_template('settings.html')


# ==================== ROTAS DE METAS ====================

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    if request.method == 'POST':
        goal_type = request.form.get('goal_type')
        target = request.form.get('target_value', type=float)
        
        if goal_type and target and target > 0:
            goal = Goal(user_id=current_user.id, goal_type=goal_type, target_value=target)
            db.session.add(goal)
            db.session.commit()
            flash('Meta criada com sucesso!', 'success')
            return redirect(url_for('goals'))
        else:
            flash('Dados inválidos para meta.', 'danger')
    
    active_goals = Goal.query.filter_by(user_id=current_user.id, achieved=False).all()
    achieved_goals = Goal.query.filter_by(user_id=current_user.id, achieved=True).all()
    
    return render_template('goals.html', active_goals=active_goals, achieved_goals=achieved_goals)


@app.route('/delete_goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        abort(403)
    db.session.delete(goal)
    db.session.commit()
    flash('Meta excluída.', 'info')
    return redirect(url_for('goals'))


# ==================== ROTAS DE RANKING ====================

@app.route('/ranking')
@login_required
def ranking():
    users = db.session.query(
        User.username,
        User.avatar,
        func.coalesce(func.sum(Run.distance_km), 0).label('total_distance'),
        func.coalesce(func.count(Run.id), 0).label('total_runs'),
        func.coalesce(func.sum(Run.duration_minutes), 0).label('total_duration')
    ).outerjoin(Run, User.id == Run.user_id)\
     .group_by(User.id, User.username, User.avatar)\
     .order_by(func.sum(Run.distance_km).desc()).all()
    
    return render_template('ranking.html', users=users)


# ==================== ROTAS SOCIAIS ====================

@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow_user(username):
    user_to_follow = User.query.filter_by(username=username).first_or_404()
    
    if user_to_follow.id == current_user.id:
        flash('Você não pode seguir a si mesmo.', 'warning')
        return redirect(url_for('public_profile', username=username))
    
    existing_follow = Follower.query.filter_by(follower_id=current_user.id, followed_id=user_to_follow.id).first()
    
    if existing_follow:
        db.session.delete(existing_follow)
        db.session.commit()
        flash(f'Você deixou de seguir {user_to_follow.username}.', 'info')
    else:
        new_follow = Follower(follower_id=current_user.id, followed_id=user_to_follow.id)
        db.session.add(new_follow)
        
        notification = Notification(
            user_id=user_to_follow.id,
            sender_id=current_user.id,
            notification_type='follow',
            message=f'{current_user.username} começou a seguir você!'
        )
        db.session.add(notification)
        
        db.session.commit()
        flash(f'Você agora está seguindo {user_to_follow.username}!', 'success')
    
    return redirect(url_for('public_profile', username=username))


@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow_user(username):
    user_to_unfollow = User.query.filter_by(username=username).first_or_404()
    
    follow = Follower.query.filter_by(follower_id=current_user.id, followed_id=user_to_unfollow.id).first()
    
    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash(f'Você deixou de seguir {user_to_unfollow.username}.', 'info')
    
    return redirect(url_for('public_profile', username=username))


@app.route('/feed')
@login_required
def activity_feed():
    following_ids = [f.followed_id for f in Follower.query.filter_by(follower_id=current_user.id).all()]
    following_ids.append(current_user.id)
    
    feed_runs = Run.query.filter(Run.user_id.in_(following_ids)).order_by(Run.date.desc()).limit(20).all()
    
    return render_template('feed.html', feed_runs=feed_runs)


@app.route('/like_run/<int:run_id>', methods=['POST'])
@login_required
def like_run(run_id):
    run = Run.query.get_or_404(run_id)
    
    existing_like = Like.query.filter_by(user_id=current_user.id, run_id=run_id).first()
    
    if existing_like:
        db.session.delete(existing_like)
        db.session.commit()
        return jsonify({'liked': False, 'count': run.get_likes_count()})
    else:
        new_like = Like(user_id=current_user.id, run_id=run_id)
        db.session.add(new_like)
        
        if run.user_id != current_user.id:
            notification = Notification(
                user_id=run.user_id,
                sender_id=current_user.id,
                notification_type='like',
                message=f'{current_user.username} curtiu sua corrida!'
            )
            db.session.add(notification)
        
        db.session.commit()
        return jsonify({'liked': True, 'count': run.get_likes_count()})


@app.route('/comment_run/<int:run_id>', methods=['POST'])
@login_required
def comment_run(run_id):
    run = Run.query.get_or_404(run_id)
    content = request.form.get('content', '').strip()
    
    if content:
        comment = Comment(user_id=current_user.id, run_id=run_id, content=content)
        db.session.add(comment)
        
        if run.user_id != current_user.id:
            notification = Notification(
                user_id=run.user_id,
                sender_id=current_user.id,
                notification_type='comment',
                message=f'{current_user.username} comentou na sua corrida: "{content[:50]}"'
            )
            db.session.add(notification)
        
        db.session.commit()
        flash('Comentário adicionado!', 'success')
    else:
        flash('O comentário não pode ser vazio.', 'danger')
    
    return redirect(url_for('run_detail', run_id=run_id))


# ==================== ROTAS DE NOTIFICAÇÕES ====================

@app.route('/notifications')
@login_required
def notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    unread_count = current_user.get_unread_notifications_count()
    return render_template('notifications.html', notifications=notifications, unread_count=unread_count)


@app.route('/notifications/read_all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    return redirect(url_for('notifications'))


@app.route('/notification/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    notification = Notification.query.get_or_404(notif_id)
    if notification.user_id != current_user.id:
        abort(403)
    notification.read = True
    db.session.commit()
    return jsonify({'success': True})


# ==================== ROTAS DE RECORDES ====================

@app.route('/personal_records')
@login_required
def personal_records():
    records = current_user.get_personal_records()
    streak = current_user.get_current_streak()
    return render_template('personal_records.html', records=records, streak=streak)


# ==================== ROTA DE EXPORTAÇÃO ====================

@app.route('/export_csv')
@login_required
def export_csv():
    runs = Run.query.filter_by(user_id=current_user.id).order_by(Run.date.desc()).all()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Data', 'Distância (km)', 'Duração (min)', 'Ritmo (min/km)', 'Velocidade (km/h)', 'Calorias', 'Percurso', 'Notas'])
    
    for r in runs:
        cw.writerow([
            r.date.strftime('%d/%m/%Y'),
            f"{r.distance_km:.2f}",
            f"{r.duration_minutes:.1f}",
            f"{r.pace:.2f}",
            f"{r.speed:.2f}",
            f"{r.calories:.0f}" if r.calories else '',
            r.route_name or '',
            r.notes or ''
        ])
    
    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=minhas_corridas.csv"})


# ==================== INICIALIZAÇÃO ====================

@app.cli.command('init-db')
def init_db_command():
    db.create_all()
    if Badge.query.count() == 0:
        seed_badges()
    print('Banco de dados inicializado com badges.')


if __name__ == '__main__':
    with app.app_context():
        db.drop_all()  # Remove todas as tabelas antigas
        db.create_all()  # Cria todas as tabelas novamente
        if Badge.query.count() == 0:
            seed_badges()
    app.run(debug=True)