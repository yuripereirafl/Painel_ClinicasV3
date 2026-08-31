from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_socketio import SocketIO, emit, join_room
from models import db, Password, Clinic, Attendant
from sqlalchemy import text
from datetime import datetime, timedelta
import pytz
from gtts import gTTS
import os
import json
import time
import csv
import io
import unicodedata
from Zimbra import zimbra
import glob
import threading
try:
    from escpos.printer import Network
except Exception:
    Network = None
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor, as_completed
from clinics_config import get_clinic_nodes

SAO_PAULO = pytz.timezone('America/Sao_Paulo')

# Lock para evitar que múltiplas threads tentem imprimir ao mesmo tempo
# e sobrescrevam o arquivo temp_ticket.png simultaneamente.
print_lock = threading.Lock()

# Carrega variáveis do arquivo .env manualmente se ele existir
if os.path.exists('.env'):
    with open('.env', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

app = Flask(__name__)

# Configuração do Banco de Dados via Variáveis de Ambiente
DB_USER = os.getenv('POSTGRES_USER', 'myuser')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'mypassword')
DB_HOST = os.getenv('POSTGRES_HOST', 'localhost') # Alterado de 'db' para 'localhost' para rodar fora do docker por padrão
DB_PORT = os.getenv('POSTGRES_PORT', '5432')
DB_NAME = os.getenv('POSTGRES_DB', 'mydatabase')

if os.getenv('USE_SQLITE') == 'true':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///painel.db'
    print("Usando Banco de Dados SQLite (Local)")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    print(f"Tentando conectar ao Postgres em {DB_HOST}")
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'mysecretkey')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Dicionário para armazenar a senha inicial por clínica
initial_passwords = {}

# Configuração da Impressora via Variáveis de Ambiente
PRINTER_IP = os.getenv('PRINTER_IP', '192.168.2.205')
APP_PORT = int(os.getenv('APP_PORT', 5000))
DEFAULT_CLINIC_ID = int(os.getenv('DEFAULT_CLINIC_ID', 1))
SCREEN_TYPE = os.getenv('SCREEN_TYPE', 'panel')

@app.route('/')
def index():
    """Redireciona automaticamente para a tela configurada no .env"""
    return redirect(url_for(SCREEN_TYPE, clinic_id=DEFAULT_CLINIC_ID))

def print_ticket(clinic_name, queue_name, password_number, queue_tag="N"):
    """Gera uma imagem de alta fidelidade e envia para a Bematech."""
    def task():
        p = None
        try:
            from PIL import Image, ImageDraw, ImageFont
            import unicodedata

            def clean_text(text):
                return "".join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))

            # Configurações do Canvas (Largura padrão 80mm ~ 576px)
            width = 576
            height = 800 # Altura inicial generosa
            background_color = 255 # Branco
            image = Image.new('L', (width, height), background_color)
            draw = ImageDraw.Draw(image)

            # Fontes (Windows e Linux/Docker)
            try:
                # Caminhos comuns para fontes
                paths = [
                    "C:\\Windows\\Fonts\\arial.ttf",      # Windows
                    "C:\\Windows\\Fonts\\arialbd.ttf",    # Windows Bold
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", # Linux/Docker
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"     # Linux/Docker Bold
                ]
                
                # Tenta Arial no Windows
                if os.name == 'nt':
                    font_path = "C:\\Windows\\Fonts\\arial.ttf"
                    font_path_bold = "C:\\Windows\\Fonts\\arialbd.ttf"
                else:
                    # Tenta Liberation no Linux (Docker)
                    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
                    font_path_bold = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

                if not os.path.exists(font_path):
                    # Fallback para qualquer fonte .ttf que existir se a específica falhar
                    font_path = font_path_bold = ImageFont.load_default()
                
                f_small = ImageFont.truetype(font_path, 24)
                f_medium = ImageFont.truetype(font_path, 32)
                f_large_bold = ImageFont.truetype(font_path_bold, 40)
                f_giant_bold = ImageFont.truetype(font_path_bold, 180) 
            except Exception as e_font:
                print(f"Erro ao carregar fontes: {e_font}")
                f_small = f_medium = f_large_bold = f_giant_bold = ImageFont.load_default()

            y_cursor = 20

            # 1. Logo (Centralizado)
            # Tenta carregar o logo.png se existir
            logo_path = "logo.png"
            if os.path.exists(logo_path):
                try:
                    logo_img = Image.open(logo_path).convert("RGBA")
                    # Prepara a imagem para impressão térmica (p&b)
                    logo_canvas = Image.new("RGB", logo_img.size, (255, 255, 255))
                    if logo_img.mode == 'RGBA':
                        logo_canvas.paste(logo_img, mask=logo_img.split()[3])
                    else:
                        logo_canvas.paste(logo_img)
                    
                    logo_canvas = logo_canvas.convert("L")
                    
                    # Redimensiona para caber no papel
                    l_width = 300
                    w_perc = (l_width / float(logo_canvas.size[0]))
                    l_height = int((float(logo_canvas.size[1]) * float(w_perc)))
                    logo_canvas = logo_canvas.resize((l_width, l_height), Image.Resampling.LANCZOS)
                    
                    image.paste(logo_canvas, ((width - l_width) // 2, y_cursor))
                    y_cursor += l_height + 20
                except Exception as e_img:
                    print(f"Erro ao carregar imagem do logo: {e_img}")

            # 2. Separador
            draw.text((20, y_cursor), "-" * 50, font=f_small, fill=0)
            y_cursor += 30

            # 3. Nome da Clínica (Removido conforme pedido anterior)
            # nome = clean_text(clinic_name).upper().replace("CLINICA", "").replace("PILOTO", "").replace(":", "").strip()
            # if not nome: nome = "CENTRAL DE CONSULTAS"
            # w_n = draw.textlength(nome, font=f_large_bold)
            # draw.text(((width - w_n) // 2, y_cursor), nome, font=f_large_bold, fill=0)
            # y_cursor += 50

            # 4. Fila (DESTAQUE EM NEGRITO)
            fila_txt = f"FILA: {clean_text(queue_name).upper()}"
            w_f = draw.textlength(fila_txt, font=f_large_bold)
            draw.text(((width - w_f) // 2, y_cursor), fila_txt, font=f_large_bold, fill=0)
            y_cursor += 60

            # 5. Separador
            draw.text((20, y_cursor), "-" * 50, font=f_small, fill=0)
            y_cursor += 30

            # 6. Label SENHA
            w_s_label = draw.textlength("SENHA", font=f_large_bold)
            draw.text(((width - w_s_label) // 2, y_cursor), "SENHA", font=f_large_bold, fill=0)
            y_cursor += 40

            # 7. Número GIGANTE
            num_txt = f"{queue_tag}{password_number:02d}"
            w_num = draw.textlength(num_txt, font=f_giant_bold)
            draw.text(((width - w_num) // 2, y_cursor), num_txt, font=f_giant_bold, fill=0)
            y_cursor += 180

            # 8. Separador
            draw.text((20, y_cursor), "-" * 50, font=f_small, fill=0)
            y_cursor += 30

            # 9. Data e Rodapé
            data_txt = f"Data: {datetime.now(SAO_PAULO).strftime('%d/%m/%Y %H:%M')}"
            w_d = draw.textlength(data_txt, font=f_medium)
            draw.text(((width - w_d) // 2, y_cursor), data_txt, font=f_medium, fill=0)
            y_cursor += 40
            
            msg = "Aguarde ser chamado no painel"
            w_m = draw.textlength(msg, font=f_medium)
            draw.text(((width - w_m) // 2, y_cursor), msg, font=f_medium, fill=0)
            y_cursor += 60

            # 10. Bloqueio para garantir que apenas uma impressão ocorra por vez
            with print_lock:
                # Salva a imagem
                image_path = f"temp_ticket_{password_number}.png"
                final_image = image.crop((0, 0, width, y_cursor + 20)).convert('1')
                final_image.save(image_path)

                print(f"Tentando enviar ticket {password_number} para a impressora {PRINTER_IP}...")
                
                # Envia para a impressora
                p = Network(PRINTER_IP, timeout=10)
                p.hw("init")
                p.image(image_path)
                p.ln(5) # Espaço vital da lâmina

                # Usaremos puramente um pulso HEX simples para acionar a alavanca da lâmina 1 vez
                p._raw(b'\x1b\x6d') # Comando genérico puro de Parcial (evitar falha da lib)
                p.close()
                
                print(f"Ticket {password_number} (IMAGEM) enviado com sucesso para {PRINTER_IP}.")
                
                # Remove o arquivo temporário
                if os.path.exists(image_path):
                    os.remove(image_path)

        except Exception as e:
            print(f"ERRO DE IMPRESSÃO GRÁFICA (Ticket {password_number}): {e}")
        finally:
            if p:
                try: p.close()
                except: pass

    # Usando socketio.start_background_task para melhor compatibilidade com eventlet
    socketio.start_background_task(task)

# Endpoint para configurar a senha inicial
@app.route('/set_initial_password', methods=['POST'])
def set_initial_password():
    """Configura a senha inicial para uma clínica."""
    data = request.json
    clinic_id = data.get('clinic_id')
    initial_password = data.get('initial_password')

    if not clinic_id or not initial_password or initial_password <= 0 or initial_password > 99:
        return {"error": "Dados inválidos"}, 400

    # Armazena a senha inicial no dicionário (usando int para garantir consistência)
    initial_passwords[int(clinic_id)] = initial_password

    return {"message": f"Senha inicial configurada para {initial_password}."}, 200

def get_today_passwords():
    """Retorna as senhas geradas hoje."""
    today = datetime.now(SAO_PAULO).date()
    return Password.query.filter_by(date=today).order_by(Password.number).all()

def get_last_password_number(clinic_id):
    """Retorna o número da última senha gerada para uma clínica."""
    last_password = Password.query.filter_by(clinic_id=clinic_id).order_by(Password.id.desc()).first()
    return last_password.number if last_password else 0


@app.route('/admin/attendants', methods=['GET', 'POST'])
def manage_attendants():
    if request.method == 'POST':
        # Captura os dados do formulário
        attendant_name = request.form.get('name')
        clinic_id = request.form.get('clinic_id')

        # Cria e salva o novo atendente
        new_attendant = Attendant(name=attendant_name, clinic_id=clinic_id)
        db.session.add(new_attendant)
        db.session.commit()

        flash(f"Atendente {attendant_name} foi criado com sucesso!", "success")
        return redirect(url_for('manage_attendants'))

    attendants = Attendant.query.all()  # Pega todos os atendentes para exibir na página
    clinics = Clinic.query.all()  # Pega todas as clínicas para o formulário
    return render_template('admin_attendants.html', attendants=attendants, clinics=clinics)


@app.route('/admin/clinics', methods=['GET', 'POST'])
def manage_clinics():
    if request.method == 'POST':
        # Captura os dados do formulário
        clinic_name = request.form.get('name')
        clinic_location = request.form.get('location')

        # Cria e salva a nova clínica
        new_clinic = Clinic(name=clinic_name, location=clinic_location)
        db.session.add(new_clinic)
        db.session.commit()

        flash(f"Clínica {clinic_name} foi criada com sucesso!", "success")
        return redirect(url_for('manage_clinics'))

    clinics = Clinic.query.all()  # Pega todas as clínicas para exibir na página
    return render_template('admin_clinics.html', clinics=clinics)


@app.route('/<int:clinic_id>/panel')
def panel(clinic_id):
    """Renderiza o painel da clínica."""
    clinic = Clinic.query.get_or_404(clinic_id)
    return render_template('panel.html', clinic=clinic)

@app.route('/<int:clinic_id>/attendant')
def attendant(clinic_id):
    """Renderiza o painel do atendente."""
    clinic = Clinic.query.get(clinic_id)
    if not clinic:
        return "Clínica não encontrada", 404
    return render_template('attendant.html', clinic=clinic)

@app.route('/api/clinic/<int:clinic_id>/waiting')
def get_waiting_passwords(clinic_id):
    """Retorna as senhas que estão aguardando hoje para a clínica."""
    today = datetime.now(SAO_PAULO).date()
    passwords = Password.query.filter_by(
        clinic_id=clinic_id,
        date=today,
        status='AGUARDANDO'
    ).order_by(Password.id.asc()).all()
    
    queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}
    
    return jsonify([{
        'number': f"{queue_tags.get(p.queue_type, 'N')}{p.number:02d}",
        'queue_type': p.queue_type,
        'id': p.id,
        'created_at': p.created_at.strftime('%H:%M:%S') if p.created_at else ''
    } for p in passwords])

@app.route('/api/clinic/<int:clinic_id>/called_today')
def get_called_today(clinic_id):
    """Retorna as últimas senhas chamadas hoje para a clínica."""
    today = datetime.now(SAO_PAULO).date()
    passwords = Password.query.filter_by(
        clinic_id=clinic_id,
        date=today,
        status='CHAMADO'
    ).order_by(Password.called_at.desc()).limit(7).all()
    
    queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}
    
    return jsonify([{
        'number': f"{queue_tags.get(p.queue_type, 'N')}{p.number:02d}",
        'queue_type': p.queue_type,
        'guiche': p.guiche,
        'called_at': p.called_at.strftime('%H:%M:%S') if p.called_at else ''
    } for p in passwords])

@app.route('/admin/reports')
def admin_reports():
    """Renderiza a página de relatórios administrativos centralizados."""
    clinics = Clinic.query.all()
    nodes = get_clinic_nodes()
    return render_template('admin_reports.html', clinics=clinics, nodes=nodes)

def calculate_local_report_data(clinic_id=1, period='today', month_str=''):
    today = datetime.now(SAO_PAULO).date()
    if period == 'today':
        start_date = today
        end_date = today
    elif period == '7days':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == '30days':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == 'custom-month' and month_str:
        try:
            year, month_num = map(int, month_str.split('-'))
            start_date = datetime(year, month_num, 1).date()
            if month_num == 12:
                next_month = datetime(year + 1, 1, 1).date()
            else:
                next_month = datetime(year, month_num + 1, 1).date()
            end_date = next_month - timedelta(days=1)
        except Exception:
            start_date = today
            end_date = today
    else:
        start_date = today
        end_date = today

    # Busca as senhas no banco local
    base_query = Password.query.filter(
        Password.date >= start_date,
        Password.date <= end_date
    )

    # Se houver senhas cadastradas para o clinic_id específico, usa ele.
    # Caso contrário, recupera todas as senhas locais do período (para bancos com 1 clínica)
    if clinic_id and base_query.filter(Password.clinic_id == clinic_id).first():
        passwords = base_query.filter(Password.clinic_id == clinic_id).all()
    else:
        passwords = base_query.all()

    # Auto-conclusão inteligente por guichê: quando uma nova senha foi chamada no mesmo guichê,
    # a anterior foi concluída naquele instante!
    guiche_passwords = {}
    for p in passwords:
        if p.guiche and p.called_at:
            g = str(p.guiche)
            if g not in guiche_passwords:
                guiche_passwords[g] = []
            guiche_passwords[g].append(p)

    has_updates = False
    for g, g_passwords in guiche_passwords.items():
        g_passwords.sort(key=lambda x: x.called_at if x.called_at else datetime.min)
        for i in range(len(g_passwords) - 1):
            curr_p = g_passwords[i]
            next_p = g_passwords[i+1]
            if curr_p.status in ('CHAMADO', 'CONCLUIDO') and next_p.called_at:
                if not curr_p.finished_at or curr_p.status == 'CHAMADO':
                    curr_p.status = 'CONCLUIDO'
                    curr_p.finished_at = next_p.called_at
                    has_updates = True

    if has_updates:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    total_generated = len(passwords)
    total_called = sum(1 for p in passwords if p.status in ('CHAMADO', 'CONCLUIDO'))
    total_finished = sum(1 for p in passwords if p.status == 'CONCLUIDO')

    wait_times = []
    attendance_times = []

    for p in passwords:
        if p.called_at and p.created_at:
            wait_min = (p.called_at - p.created_at).total_seconds() / 60.0
            wait_times.append(wait_min)
        if p.finished_at and p.called_at:
            attend_min = (p.finished_at - p.called_at).total_seconds() / 60.0
            attendance_times.append(attend_min)

    avg_wait = round(sum(wait_times) / len(wait_times), 1) if wait_times else 0.0
    avg_attend = round(sum(attendance_times) / len(attendance_times), 1) if attendance_times else 0.0

    queue_summary = {}
    for p in passwords:
        q_type = p.queue_type
        if q_type not in queue_summary:
            queue_summary[q_type] = {'total': 0, 'called': 0, 'finished': 0, 'wait_times': []}
        
        queue_summary[q_type]['total'] += 1
        if p.status in ('CHAMADO', 'CONCLUIDO'):
            queue_summary[q_type]['called'] += 1
        if p.status == 'CONCLUIDO':
            queue_summary[q_type]['finished'] += 1

        if p.called_at and p.created_at:
            wait_min = (p.called_at - p.created_at).total_seconds() / 60.0
            queue_summary[q_type]['wait_times'].append(wait_min)

    queue_list = []
    for q_type, stats in queue_summary.items():
        w_times = stats['wait_times']
        avg_w = round(sum(w_times) / len(w_times), 1) if w_times else 0.0
        queue_list.append({
            'queue_type': q_type,
            'total': stats['total'],
            'called': stats['called'],
            'finished': stats['finished'],
            'avg_wait': avg_w
        })

    guiche_summary = {}
    for p in passwords:
        if not p.guiche:
            continue
        g = p.guiche
        if g not in guiche_summary:
            guiche_summary[g] = {'total': 0, 'finished': 0, 'attendance_times': []}
        
        guiche_summary[g]['total'] += 1
        if p.status == 'CONCLUIDO':
            guiche_summary[g]['finished'] += 1
        
        if p.finished_at and p.called_at:
            attend_min = (p.finished_at - p.called_at).total_seconds() / 60.0
            guiche_summary[g]['attendance_times'].append(attend_min)

    guiche_list = []
    for g, stats in guiche_summary.items():
        a_times = stats['attendance_times']
        avg_a = round(sum(a_times) / len(a_times), 1) if a_times else 0.0
        guiche_list.append({
            'guiche': g,
            'total': stats['total'],
            'finished': stats['finished'],
            'avg_attendance': avg_a
        })

    def get_guiche_sort_key(item):
        val = item['guiche']
        try:
            return (0, int(val))
        except (ValueError, TypeError):
            return (1, str(val))
    
    guiche_list.sort(key=get_guiche_sort_key)

    return {
        'total_generated': total_generated,
        'total_called': total_called,
        'total_finished': total_finished,
        'avg_wait': avg_wait,
        'avg_attendance': avg_attend,
        'queues': queue_list,
        'guiches': guiche_list,
        'raw_wait_times': wait_times,
        'raw_attendance_times': attendance_times
    }

def fetch_single_node_data(node, period='today', month_str=''):
    """Busca os dados de relatórios de um nó (clínica)."""
    node_id = node.get('id')
    node_name = node.get('name')
    node_ip = node.get('ip')
    node_url = node.get('url')
    clinic_id = node.get('clinic_id', 1)
    is_local = node.get('is_local', False)

    # Identificação flexível de nó local (via env LOCAL_NODE_ID, DEFAULT_CLINIC_ID ou IP/host)
    local_node_id = int(os.getenv('LOCAL_NODE_ID', 0))
    clean_url = node_url.rstrip('/') if node_url else ''

    # Se for o nó local (mesma instância rodando), usa cálculo do BD direto
    if is_local or node_id == local_node_id or '127.0.0.1' in clean_url or 'localhost' in clean_url:
        try:
            with app.app_context():
                data = calculate_local_report_data(clinic_id, period, month_str)
                data['node_id'] = node_id
                data['name'] = node_name
                data['ip'] = node_ip
                data['status'] = 'online'
                return data
        except Exception as e:
            print(f"Erro ao calcular dados locais para nó {node_name}: {e}")

        # Para nós remotos via VPN, faz HTTP GET na API da clínica com timeout de 15.0s
    try:
        url = f"{clean_url}/api/reports/data?clinic_id={clinic_id}&period={period}"
        if period == 'custom-month' and month_str:
            url += f"&month={month_str}"

        req = Request(url, headers={'User-Agent': 'PainelCentral/3.0'})
        with urlopen(req, timeout=15.0) as resp:
            if resp.status == 200:
                body = resp.read().decode('utf-8')
                data = json.loads(body)
                data['node_id'] = node_id
                data['name'] = node_name
                data['ip'] = node_ip
                data['status'] = 'online'
                return data
    except Exception as e:
        print(f"Nó {node_name} ({node_ip}) inacessível/offline: {e}")

    return {
        'node_id': node_id,
        'name': node_name,
        'ip': node_ip,
        'status': 'offline',
        'total_generated': 0,
        'total_called': 0,
        'total_finished': 0,
        'avg_wait': 0.0,
        'avg_attendance': 0.0,
        'queues': [],
        'guiches': [],
        'raw_wait_times': [],
        'raw_attendance_times': []
    }

@app.route('/api/reports/data')
def get_reports_data():
    clinic_id = request.args.get('clinic_id', default=1, type=int)
    period = request.args.get('period', 'today')
    month = request.args.get('month', '')
    data = calculate_local_report_data(clinic_id, period, month)
    return jsonify(data)

@app.route('/api/central/reports/data')
def get_central_reports_data():
    node_id_param = request.args.get('node_id', 'all')
    period = request.args.get('period', 'today')
    month_str = request.args.get('month', '')

    nodes = get_clinic_nodes()

    # Se selecionou um nó/clínica específica
    if node_id_param != 'all':
        selected_node = next((n for n in nodes if str(n['id']) == str(node_id_param)), None)
        if selected_node:
            node_data = fetch_single_node_data(selected_node, period, month_str)
            guiches = node_data.get('guiches', [])
            for g in guiches:
                g['clinic_name'] = selected_node.get('name', 'Clínica')
            return jsonify({
                'is_central': False,
                'total_generated': node_data.get('total_generated', 0),
                'total_called': node_data.get('total_called', 0),
                'total_finished': node_data.get('total_finished', 0),
                'avg_wait': node_data.get('avg_wait', 0.0),
                'avg_attendance': node_data.get('avg_attendance', 0.0),
                'queues': node_data.get('queues', []),
                'guiches': guiches,
                'clinics_summary': [node_data]
            })

    # Caso seja 'all' (Todas as Clínicas - Visão Centralizada)
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_single_node_data, node, period, month_str): node for node in nodes}
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                print(f"Erro ao buscar nó: {e}")

    results.sort(key=lambda x: x.get('node_id', 0))

    total_generated = sum(r.get('total_generated', 0) for r in results)
    total_called = sum(r.get('total_called', 0) for r in results)
    total_finished = sum(r.get('total_finished', 0) for r in results)

    all_wait_times = []
    all_attend_times = []
    for r in results:
        all_wait_times.extend(r.get('raw_wait_times', []))
        all_attend_times.extend(r.get('raw_attendance_times', []))

    avg_wait = round(sum(all_wait_times) / len(all_wait_times), 1) if all_wait_times else 0.0
    avg_attend = round(sum(all_attend_times) / len(all_attend_times), 1) if all_attend_times else 0.0

    combined_queues = {}
    for r in results:
        for q in r.get('queues', []):
            qt = q['queue_type']
            if qt not in combined_queues:
                combined_queues[qt] = {'total': 0, 'called': 0, 'finished': 0, 'avg_waits': []}
            combined_queues[qt]['total'] += q['total']
            combined_queues[qt]['called'] += q['called']
            combined_queues[qt]['finished'] += q['finished']
            if 'avg_wait' in q and q['avg_wait'] > 0:
                combined_queues[qt]['avg_waits'].append(q['avg_wait'])

    queue_list = []
    for qt, stats in combined_queues.items():
        aw = round(sum(stats['avg_waits']) / len(stats['avg_waits']), 1) if stats['avg_waits'] else 0.0
        queue_list.append({
            'queue_type': qt,
            'total': stats['total'],
            'called': stats['called'],
            'finished': stats['finished'],
            'avg_wait': aw
        })

    combined_guiches = {}
    for r in results:
        clinic_name = r.get('name', 'Desconhecida')
        for g in r.get('guiches', []):
            gname = g['guiche']
            key = f"{clinic_name} - {gname}"
            if key not in combined_guiches:
                combined_guiches[key] = {'guiche': gname, 'clinic_name': clinic_name, 'total': 0, 'finished': 0, 'avg_attends': []}
            combined_guiches[key]['total'] += g['total']
            combined_guiches[key]['finished'] += g['finished']
            if 'avg_attendance' in g and g['avg_attendance'] > 0:
                combined_guiches[key]['avg_attends'].append(g['avg_attendance'])

    guiche_list = []
    for key, stats in combined_guiches.items():
        aa = round(sum(stats['avg_attends']) / len(stats['avg_attends']), 1) if stats['avg_attends'] else 0.0
        guiche_list.append({
            'guiche': stats['guiche'],
            'clinic_name': stats['clinic_name'],
            'total': stats['total'],
            'finished': stats['finished'],
            'avg_attendance': aa
        })

    def get_guiche_sort_key(item):
        clinic = item.get('clinic_name', '')
        val = item['guiche']
        try:
            return (0, int(val), clinic)
        except (ValueError, TypeError):
            return (1, str(val), clinic)
    
    guiche_list.sort(key=get_guiche_sort_key)

    return jsonify({
        'is_central': True,
        'total_generated': total_generated,
        'total_called': total_called,
        'total_finished': total_finished,
        'avg_wait': avg_wait,
        'avg_attendance': avg_attend,
        'queues': queue_list,
        'guiches': guiche_list,
        'clinics_summary': results
    })

def get_local_passwords_list(clinic_id=1, period='today', month_str=''):
    today = datetime.now(SAO_PAULO).date()
    if period == 'today':
        start_date = today
        end_date = today
    elif period == '7days':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == '30days':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == 'custom-month' and month_str:
        try:
            year, month_num = map(int, month_str.split('-'))
            start_date = datetime(year, month_num, 1).date()
            if month_num == 12:
                next_month = datetime(year + 1, 1, 1).date()
            else:
                next_month = datetime(year, month_num + 1, 1).date()
            end_date = next_month - timedelta(days=1)
        except Exception:
            start_date = today
            end_date = today
    else:
        start_date = today
        end_date = today

    base_query = Password.query.filter(
        Password.date >= start_date,
        Password.date <= end_date
    )

    if clinic_id and base_query.filter(Password.clinic_id == clinic_id).first():
        passwords = base_query.filter(Password.clinic_id == clinic_id).order_by(Password.id.asc()).all()
    else:
        passwords = base_query.order_by(Password.id.asc()).all()

    guiche_passwords = {}
    for p in passwords:
        if p.guiche and p.called_at:
            g = str(p.guiche)
            if g not in guiche_passwords:
                guiche_passwords[g] = []
            guiche_passwords[g].append(p)

    has_updates = False
    for g, g_passwords in guiche_passwords.items():
        g_passwords.sort(key=lambda x: x.called_at if x.called_at else datetime.min)
        for i in range(len(g_passwords) - 1):
            curr_p = g_passwords[i]
            next_p = g_passwords[i+1]
            if curr_p.status in ('CHAMADO', 'CONCLUIDO') and next_p.called_at:
                if not curr_p.finished_at or curr_p.status == 'CHAMADO':
                    curr_p.status = 'CONCLUIDO'
                    curr_p.finished_at = next_p.called_at
                    has_updates = True

    if has_updates:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return passwords

@app.route('/api/reports/passwords_detail')
def get_passwords_detail():
    clinic_id = request.args.get('clinic_id', default=1, type=int)
    period = request.args.get('period', 'today')
    month = request.args.get('month', '')
    passwords = get_local_passwords_list(clinic_id, period, month)
    queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}
    out = []
    for p in passwords:
        prefix = queue_tags.get(p.queue_type, 'N')
        out.append({
            'id': p.id,
            'date': p.date.strftime('%d/%m/%Y') if p.date else '',
            'ticket': f"{prefix}{p.number:02d}",
            'queue_type': p.queue_type,
            'guiche': p.guiche if p.guiche else '',
            'status': p.status,
            'created_at': p.created_at.strftime('%H:%M:%S') if p.created_at else '',
            'called_at': p.called_at.strftime('%H:%M:%S') if p.called_at else '',
            'finished_at': p.finished_at.strftime('%H:%M:%S') if p.finished_at else '',
            'wait_min': round((p.called_at - p.created_at).total_seconds() / 60.0, 1) if p.called_at and p.created_at else None,
            'attend_min': round((p.finished_at - p.called_at).total_seconds() / 60.0, 1) if p.finished_at and p.called_at else None
        })
    return jsonify(out)

def format_duration(minutes):
    try:
        val = float(minutes)
    except (ValueError, TypeError):
        val = 0.0

    if val <= 0:
        return "0 min"
    if val < 60:
        return f"{round(val, 1)} min"

    hours = int(val // 60)
    mins = int(round(val % 60))
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins:02d}min"

@app.route('/api/reports/send_email', methods=['POST'])
def send_report_email():
    data = request.json or {}
    node_id_param = str(data.get('node_id') or data.get('clinic_id') or 'all')
    period = data.get('period', 'today')
    month_str = data.get('month', '')
    recipient = data.get('recipient')

    if not recipient:
        return jsonify({'error': 'Destinatário do e-mail é obrigatório'}), 400

    nodes = get_clinic_nodes()
    today = datetime.now(SAO_PAULO).date()

    if period == 'today':
        period_label = f"Hoje ({today.strftime('%d/%m/%Y')})"
    elif period == '7days':
        start_date = today - timedelta(days=7)
        period_label = f"Últimos 7 dias ({start_date.strftime('%d/%m/%Y')} a {today.strftime('%d/%m/%Y')})"
    elif period == '30days':
        start_date = today - timedelta(days=30)
        period_label = f"Último mês ({start_date.strftime('%d/%m/%Y')} a {today.strftime('%d/%m/%Y')})"
    elif period == 'custom-month' and month_str:
        period_label = f"Mês {month_str}"
    else:
        period_label = f"Hoje ({today.strftime('%d/%m/%Y')})"

    all_passwords_for_csv = []

    if node_id_param != 'all':
        selected_node = next((n for n in nodes if str(n['id']) == str(node_id_param)), None)
        clinic_name = selected_node['name'] if selected_node else "Clínica Local"
        if selected_node:
            report_data = fetch_single_node_data(selected_node, period, month_str)
            # Busca lista detalhada do nó
            node_url = selected_node.get('url', '').rstrip('/')
            node_id = selected_node.get('id')
            local_node_id = int(os.getenv('LOCAL_NODE_ID', 0))
            if selected_node.get('is_local') or node_id == local_node_id or '127.0.0.1' in node_url or 'localhost' in node_url:
                local_pwds = get_local_passwords_list(selected_node.get('clinic_id', 1), period, month_str)
                for p in local_pwds:
                    all_passwords_for_csv.append((p, clinic_name))
            else:
                try:
                    url = f"{node_url}/api/reports/passwords_detail?clinic_id={selected_node.get('clinic_id', 1)}&period={period}"
                    if period == 'custom-month' and month_str:
                        url += f"&month={month_str}"
                    req = Request(url, headers={'User-Agent': 'PainelCentral/3.0'})
                    with urlopen(req, timeout=15.0) as resp:
                        if resp.status == 200:
                            data_list = json.loads(resp.read().decode('utf-8'))
                            for d in data_list:
                                d['unit_name'] = clinic_name
                                all_passwords_for_csv.append((d, clinic_name))
                except Exception as e:
                    print(f"Erro ao buscar CSV remoto de {clinic_name}: {e}")
        else:
            report_data = calculate_local_report_data(1, period, month_str)
            local_pwds = get_local_passwords_list(1, period, month_str)
            for p in local_pwds:
                all_passwords_for_csv.append((p, clinic_name))
    else:
        clinic_name = "Todas as Clínicas (Visão Centralizada)"
        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_single_node_data, node, period, month_str): node for node in nodes}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    results.append(res)
                except Exception:
                    pass

        results.sort(key=lambda x: x.get('node_id', 0))

        total_gen = sum(r.get('total_generated', 0) for r in results)
        total_call = sum(r.get('total_called', 0) for r in results)
        total_fin = sum(r.get('total_finished', 0) for r in results)
        
        all_waits = []
        all_attends = []
        for r in results:
            all_waits.extend(r.get('raw_wait_times', []))
            all_attends.extend(r.get('raw_attendance_times', []))

        avg_w = round(sum(all_waits) / len(all_waits), 1) if all_waits else 0.0
        avg_a = round(sum(all_attends) / len(all_attends), 1) if all_attends else 0.0

        clinics_rows_html = ""
        for r in results:
            st = "Online" if r.get('status') == 'online' else "Offline"
            clinics_rows_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: left;"><strong>{r.get('name')}</strong></td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{st}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{r.get('total_generated', 0)}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{r.get('total_called', 0)}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{r.get('total_finished', 0)}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center; color: #3E8FF7;">{format_duration(r.get('avg_wait', 0.0))}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center; color: #F4B400;">{format_duration(r.get('avg_attendance', 0.0))}</td>
            </tr>
            """

        report_data = {
            'total_generated': total_gen,
            'total_called': total_call,
            'total_finished': total_fin,
            'avg_wait': avg_w,
            'avg_attendance': avg_a,
            'queues': [],
            'guiches': [],
            'clinics_rows_html': clinics_rows_html
        }

        # Coleta os registros detalhados de todas as clínicas para o CSV centralizado
        local_node_id = int(os.getenv('LOCAL_NODE_ID', 0))
        for node in nodes:
            c_name = node.get('name')
            node_url = node.get('url', '').rstrip('/')
            node_id = node.get('id')
            if node.get('is_local') or node_id == local_node_id or '127.0.0.1' in node_url or 'localhost' in node_url:
                local_pwds = get_local_passwords_list(node.get('clinic_id', 1), period, month_str)
                for p in local_pwds:
                    all_passwords_for_csv.append((p, c_name))
            else:
                try:
                    url = f"{node_url}/api/reports/passwords_detail?clinic_id={node.get('clinic_id', 1)}&period={period}"
                    if period == 'custom-month' and month_str:
                        url += f"&month={month_str}"
                    req = Request(url, headers={'User-Agent': 'PainelCentral/3.0'})
                    with urlopen(req, timeout=15.0) as resp:
                        if resp.status == 200:
                            data_list = json.loads(resp.read().decode('utf-8'))
                            for d in data_list:
                                d['unit_name'] = c_name
                                all_passwords_for_csv.append((d, c_name))
                except Exception as e:
                    print(f"Erro ao buscar CSV de {c_name}: {e}")

    total_generated = report_data.get('total_generated', 0)
    total_called = report_data.get('total_called', 0)
    total_finished = report_data.get('total_finished', 0)
    avg_wait = report_data.get('avg_wait', 0.0)
    avg_attend = report_data.get('avg_attendance', 0.0)

    queue_rows_html = ""
    for q in report_data.get('queues', []):
        queue_rows_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: left;">{q.get('queue_type')}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{q.get('total')}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{q.get('finished')}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{format_duration(q.get('avg_wait'))}</td>
        </tr>
        """

    guiche_rows_html = ""
    for g in report_data.get('guiches', []):
        guiche_rows_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: left;">{g.get('clinic_name', clinic_name)}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: left;">{g.get('guiche')}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{g.get('total')}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{g.get('finished')}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: center;">{format_duration(g.get('avg_attendance'))}</td>
        </tr>
        """

    clinics_table_section = f"""
    <h3 style="color: #073A7A; margin-top: 25px;">Desempenho por Clínica</h3>
    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
        <thead style="background: #f4f6f9;">
            <tr>
                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Clínica</th>
                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Status</th>
                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Geradas</th>
                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Chamadas</th>
                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Concluídas</th>
                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Espera Média</th>
                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Atendimento</th>
            </tr>
        </thead>
        <tbody>{report_data.get('clinics_rows_html', '')}</tbody>
    </table>
    """ if 'clinics_rows_html' in report_data else ""

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; background-color: #f4f6f9; padding: 20px;">
        <div style="max-width: 650px; margin: 0 auto; background: #fff; padding: 25px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.05); border-top: 8px solid #073A7A;">
            <h2 style="color: #073A7A; margin-top: 0;">Relatório de Atendimentos</h2>
            <p><strong>Unidade:</strong> {clinic_name}</p>
            <p><strong>Período:</strong> {period_label}</p>
            
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            
            <h3 style="color: #073A7A;">Indicadores Gerais</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr>
                    <td style="padding: 8px 0;"><strong>Total de Senhas Geradas:</strong></td>
                    <td style="text-align: right;">{total_generated}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;"><strong>Total de Senhas Chamadas:</strong></td>
                    <td style="text-align: right;">{total_called}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0;"><strong>Total de Atendimentos Concluídos:</strong></td>
                    <td style="text-align: right;">{total_finished}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #3E8FF7;"><strong>Tempo Médio de Espera (Fila):</strong></td>
                    <td style="text-align: right; color: #3E8FF7;"><strong>{format_duration(avg_wait)}</strong></td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #F4B400;"><strong>Tempo Médio de Guichê (Atendimento):</strong></td>
                    <td style="text-align: right; color: #F4B400;"><strong>{format_duration(avg_attend)}</strong></td>
                </tr>
            </table>

            {clinics_table_section}

            {f'<h3 style="color: #073A7A;">Resumo por Tipo de Fila</h3><table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;"><thead style="background: #f4f6f9;"><tr><th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Fila</th><th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Geradas</th><th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Concluídas</th><th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Espera Média</th></tr></thead><tbody>{queue_rows_html}</tbody></table>' if queue_rows_html else ''}
            
            {f'<h3 style="color: #073A7A;">Resumo por Guichê</h3><table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;"><thead style="background: #f4f6f9;"><tr><th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Clínica</th><th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Guichê</th><th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Chamadas</th><th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Concluídas</th><th style="padding: 10px; text-align: center; border-bottom: 2px solid #ddd;">Tempo Médio</th></tr></thead><tbody>{guiche_rows_html}</tbody></table>' if guiche_rows_html else ''}
            
            <div style="background-color: #e7f3ff; color: #1d5287; padding: 15px; border-radius: 6px; margin-top: 20px; font-size: 14px;">
                <strong>Nota:</strong> O relatório detalhado com cada uma das senhas, horários de criação, chamada e conclusão está anexado a este e-mail como arquivo <code>.csv</code>.
            </div>

            <p style="font-size: 12px; color: #777; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px; text-align: center;">
                Painel de Senhas v3 - Gerador automático de relatórios
            </p>
        </div>
    </body>
    </html>
    """

    z = zimbra()
    subject = f"Relatório de Atendimento - {clinic_name} - {period_label}"
    clinic_name_clean = "".join(c for c in unicodedata.normalize('NFKD', clinic_name) if not unicodedata.combining(c)).lower().replace(' ', '_')
    filename = f"relatorio_{clinic_name_clean}_{period}.csv"
    
    # Gera o CSV Detalhado com as 12 colunas da imagem do usuário
    output = io.StringIO()
    output.write('\ufeff') # BOM do Excel UTF-8
    writer = csv.writer(output, delimiter=';')
    
    writer.writerow([
        'Unidade',
        'ID da Senha',
        'Data',
        'Senha',
        'Tipo de Fila',
        'Guichê',
        'Status',
        'Gerada em',
        'Chamada em',
        'Concluída em',
        'Tempo de Espera (min)',
        'Tempo de Atendimento (min)'
    ])

    queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}

    for item, unit_n in all_passwords_for_csv:
        if isinstance(item, dict):
            p_id = item.get('id', '')
            p_date = item.get('date', '')
            p_ticket = item.get('ticket', '')
            p_queue = item.get('queue_type', '')
            p_guiche = item.get('guiche', '')
            p_status = item.get('status', '')
            p_created = item.get('created_at', '')
            p_called = item.get('called_at', '')
            p_finished = item.get('finished_at', '')
            p_wait = str(item.get('wait_min', '')).replace('.', ',') if item.get('wait_min') is not None else ''
            p_attend = str(item.get('attend_min', '')).replace('.', ',') if item.get('attend_min') is not None else ''
        else:
            p = item
            p_id = p.id
            p_date = p.date.strftime('%d/%m/%Y') if p.date else ''
            prefix = queue_tags.get(p.queue_type, 'N')
            p_ticket = f"{prefix}{p.number:02d}"
            p_queue = p.queue_type
            p_guiche = p.guiche if p.guiche else ''
            p_status = p.status
            p_created = p.created_at.strftime('%H:%M:%S') if p.created_at else ''
            p_called = p.called_at.strftime('%H:%M:%S') if p.called_at else ''
            p_finished = p.finished_at.strftime('%H:%M:%S') if p.finished_at else ''
            p_wait = str(round((p.called_at - p.created_at).total_seconds() / 60.0, 1)).replace('.', ',') if p.called_at and p.created_at else ''
            p_attend = str(round((p.finished_at - p.called_at).total_seconds() / 60.0, 1)).replace('.', ',') if p.finished_at and p.called_at else ''

        writer.writerow([
            unit_n, p_id, p_date, p_ticket, p_queue, p_guiche, p_status, p_created, p_called, p_finished, p_wait, p_attend
        ])

    csv_data = output.getvalue().encode('utf-8')
    output.close()

    sucesso = z.enviar_com_anexo(recipient, subject, html_body, csv_data, filename)

    if sucesso:
        return jsonify({'message': 'E-mail enviado com sucesso'}), 200
    else:
        return jsonify({'error': 'Falha ao enviar e-mail via servidor Zimbra'}), 500

@app.route('/<int:clinic_id>/tablet')
def tablet(clinic_id):
    """Renderiza a tela do tablet para geração de senhas."""
    clinic = Clinic.query.get_or_404(clinic_id)
    return render_template('tablet.html', clinic=clinic)

@socketio.on('generate_password')
def generate_password(data):
    """Gera uma nova senha via totem ou manualmente."""
    clinic_id = data.get('clinic_id')
    queue_type = data.get('queue_type', 'NORMAL')
    guiche = data.get('guiche') # Se vier do atendente, já tem guichê

    if not clinic_id:
        return

    # Log do IP para identificar a origem
    ip_origem = request.remote_addr if request else "Desconhecido"
    print(f"Solicitação de senha recebida do IP: {ip_origem} para Clínica: {clinic_id}")

    clinic_id = int(clinic_id)
    clinic = Clinic.query.get(clinic_id)
    
    # Obtém a data local do servidor (mais intuitivo para clínicas locais)
    today = datetime.now(SAO_PAULO).date()
    
    # Busca a última senha gerada para esta clínica (independente do dia)
    last_password = Password.query.filter_by(clinic_id=clinic_id).order_by(Password.id.desc()).first()

    if last_password and last_password.date == today:
        if last_password.number >= 99:
            new_password_number = 1
        else:
            new_password_number = int(last_password.number) + 1
    else:
        # Se for o primeiro do dia ou não houver senhas anteriores
        new_password_number = initial_passwords.get(clinic_id, 1)

    print(f"DEBUG NOVO: Clínica {clinic_id} | Data {today} | Última do BD: {last_password.number if last_password else 'Nenhuma'} ({last_password.date if last_password else '-'}) -> Nova: {new_password_number}")

    # Salva a nova senha no banco de dados
    status = 'CHAMADO' if guiche else 'AGUARDANDO'
    password = Password(
        number=new_password_number, 
        queue_type=queue_type, 
        status=status, 
        guiche=guiche, 
        date=today, 
        clinic_id=clinic_id
    )
    password.created_at = datetime.now(SAO_PAULO)
    if status == 'CHAMADO':
        password.called_at = datetime.now(SAO_PAULO)

    db.session.add(password)
    db.session.commit()

    # Imprimir ticket se for geração via totem (sem guichê inicial)
    if not guiche:
        queue_names = {
            'NORMAL': 'Normal',
            'PRIORITARIA': 'Prioritária',
            'DR_CENTRAL': 'DR Central',
            'ODONTO': 'Odonto'
        }
        queue_tags = {
            'NORMAL': 'N',
            'PRIORITARIA': 'P',
            'DR_CENTRAL': 'D',
            'ODONTO': 'O'
        }
        print_ticket(clinic.name, queue_names.get(queue_type, 'Normal'), new_password_number, queue_tags.get(queue_type, 'N'))

    # Emitir evento se já for chamado
    if status == 'CHAMADO':
        queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}
        prefix = queue_tags.get(queue_type, 'N')
        emit('new_password', {
            'password': f"{prefix}{new_password_number:02d}", 
            'guiche': guiche, 
            'queue_type': queue_type
        }, broadcast=True, room=f"clinic_{clinic_id}")
    
    # Notifica que a fila de espera mudou
    emit('queue_updated', {'clinic_id': clinic_id}, broadcast=True, room=f"clinic_{clinic_id}")

@socketio.on('call_any')
def call_any(data):
    """Atendente chama a próxima senha disponível (qualquer fila)."""
    clinic_id = data.get('clinic_id')
    guiche = data.get('guiche')

    if not clinic_id or not guiche:
        return

    today = datetime.now(SAO_PAULO).date()
    now = datetime.now(SAO_PAULO)

    # Auto-conclui a senha anterior que estava em atendimento neste guichê
    prev_active = Password.query.filter_by(
        clinic_id=clinic_id,
        guiche=guiche,
        status='CHAMADO',
        date=today
    ).first()

    if prev_active:
        prev_active.status = 'CONCLUIDO'
        prev_active.finished_at = now

    # Busca a próxima senha aguardando com o menor ID (ordem de chegada rigorosa)
    next_password = Password.query.filter_by(
        clinic_id=clinic_id, 
        status='AGUARDANDO',
        date=today
    ).order_by(Password.id.asc()).first()

    if next_password:
        next_password.status = 'CHAMADO'
        next_password.guiche = guiche
        next_password.called_at = now
        db.session.commit()

        queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}
        prefix = queue_tags.get(next_password.queue_type, 'N')

        emit('new_password', {
            'password': f"{prefix}{next_password.number:02d}", 
            'guiche': guiche, 
            'queue_type': next_password.queue_type
        }, broadcast=True, room=f"clinic_{clinic_id}")

        # Notifica que a fila de espera mudou
        emit('queue_updated', {'clinic_id': clinic_id}, broadcast=True, room=f"clinic_{clinic_id}")
    else:
        db.session.commit()
        emit('no_passwords', {'queue_type': 'TODAS'}, room=request.sid)

@socketio.on('call_next')
def call_next(data):
    """Atendente chama a próxima senha de uma determinada fila."""
    clinic_id = data.get('clinic_id')
    guiche = data.get('guiche')
    queue_type = data.get('queue_type')

    if not clinic_id or not guiche or not queue_type:
        return

    today = datetime.now(SAO_PAULO).date()
    now = datetime.now(SAO_PAULO)

    # Auto-conclui a senha anterior que estava em atendimento neste guichê
    prev_active = Password.query.filter_by(
        clinic_id=clinic_id,
        guiche=guiche,
        status='CHAMADO',
        date=today
    ).first()

    if prev_active:
        prev_active.status = 'CONCLUIDO'
        prev_active.finished_at = now

    # Busca a próxima senha aguardando para este tipo de fila
    next_password = Password.query.filter_by(
        clinic_id=clinic_id, 
        queue_type=queue_type, 
        status='AGUARDANDO',
        date=today
    ).order_by(Password.id.asc()).first()

    if next_password:
        next_password.status = 'CHAMADO'
        next_password.guiche = guiche
        next_password.called_at = now
        db.session.commit()

        queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}
        prefix = queue_tags.get(queue_type, 'N')

        emit('new_password', {
            'password': f"{prefix}{next_password.number:02d}", 
            'guiche': guiche, 
            'queue_type': queue_type
        }, broadcast=True, room=f"clinic_{clinic_id}")
        
        # Notifica que a fila de espera mudou
        emit('queue_updated', {'clinic_id': clinic_id}, broadcast=True, room=f"clinic_{clinic_id}")
        
        print(f"Password {next_password.number} ({queue_type}) called at guiche {guiche}")
    else:
        db.session.commit()
        emit('no_passwords', {'queue_type': queue_type}, room=request.sid)


@socketio.on('call_by_name')
def call_by_name(data):
    """Chama um paciente pelo nome e emite o evento para o painel."""
    clinic_id = data.get('clinic_id')
    name = data.get('name')
    guiche = data.get('guiche')

    if not clinic_id or not name or not guiche:
        print("Dados insuficientes para chamar pelo nome.")
        return

    # Emitir o evento para todos os clientes na sala da clínica
    room = f"clinic_{clinic_id}"
    emit('name_called', {'name': name, 'guiche': guiche}, room=room)
    print(f"Paciente {name} chamado no guichê {guiche} para a clínica {clinic_id}")

@socketio.on('name_called')
def handle_name_called(data):
    clinic_id = data.get('clinic_id')
    name = data.get('name')
    guiche = data.get('guiche')

    if clinic_id and name and guiche:
        # Emitir o evento para o painel
        emit('name_called', {'name': name, 'guiche': guiche}, room=f"clinic_{clinic_id}")

@socketio.on('join')
def handle_join(data):
    """Cliente entra na sala da clínica para receber atualizações."""
    clinic_id = data.get('clinic_id')
    if clinic_id:
        room = f"clinic_{clinic_id}"
        join_room(room)
        print(f"Painel conectado à sala {room}")

@socketio.on('conclude_attendance')
def conclude_attendance(data):
    """Marca o atendimento atual como concluído."""
    clinic_id = data.get('clinic_id')
    guiche = data.get('guiche')

    if not clinic_id or not guiche:
        return

    today = datetime.now(SAO_PAULO).date()
    # Busca o atendimento ativo (CHAMADO) para este guichê nesta clínica hoje
    active_password = Password.query.filter_by(
        clinic_id=clinic_id,
        guiche=guiche,
        status='CHAMADO',
        date=today
    ).order_by(Password.called_at.desc()).first()

    if active_password:
        active_password.status = 'CONCLUIDO'
        active_password.finished_at = datetime.now(SAO_PAULO)
        db.session.commit()
        print(f"Senha {active_password.number} no guichê {guiche} marcada como CONCLUIDA às {active_password.finished_at}")

def limpar_audios_antigos(pasta, segundos=3600):
    """Remove arquivos da pasta com mais de 'segundos' de idade."""
    agora = time.time()
    for arquivo in glob.glob(os.path.join(pasta, '*.mp3')):
        if os.path.isfile(arquivo):
            if agora - os.path.getmtime(arquivo) > segundos:
                try:
                    os.remove(arquivo)
                except Exception as e:
                    print(f"Erro ao remover {arquivo}: {e}")

@app.route('/api/tts', methods=['POST'])
def tts():
    """Gera áudio TTS para o texto enviado e retorna a URL do arquivo."""
    data = request.json
    texto = data.get('texto')
    if not texto:
        return jsonify({'error': 'Texto não informado'}), 400

    # Gera um nome de arquivo único
    filename = f'chamada_{int(time.time()*1000)}.mp3'
    pasta_tts = os.path.join('static', 'tts')
    os.makedirs(pasta_tts, exist_ok=True)

    # Limpa arquivos antigos (mais de 1 hora)
    limpar_audios_antigos(pasta_tts, segundos=3600)

    caminho = os.path.join(pasta_tts, filename)

    # Gera o áudio
    tts = gTTS(text=texto, lang='pt-br')
    tts.save(caminho)

    return jsonify({'url': f'/static/tts/{filename}'})

if __name__ == '__main__':
    with app.app_context():
        print("CRIANDO TABELAS")
        db.create_all()
        
        # Garante que a coluna 'created_at' existe na tabela 'password'
        try:
            db.session.execute(text("SELECT created_at FROM password LIMIT 1;"))
        except Exception:
            db.session.rollback()
            try:
                db.session.execute(text("ALTER TABLE password ADD COLUMN created_at TIMESTAMP;"))
                db.session.commit()
                print("Coluna 'created_at' adicionada com sucesso à tabela 'password'.")
            except Exception as e:
                db.session.rollback()
                print(f"Erro ao adicionar coluna 'created_at': {e}")

        # Garante que a coluna 'finished_at' existe na tabela 'password'
        try:
            db.session.execute(text("SELECT finished_at FROM password LIMIT 1;"))
        except Exception:
            db.session.rollback()
            try:
                db.session.execute(text("ALTER TABLE password ADD COLUMN finished_at TIMESTAMP;"))
                db.session.commit()
                print("Coluna 'finished_at' adicionada com sucesso à tabela 'password'.")
            except Exception as e:
                db.session.rollback()
                print(f"Erro ao adicionar coluna 'finished_at': {e}")
                
        # Cria uma clínica padrão se não houver nenhuma
        if not Clinic.query.first():
            default_clinic = Clinic(name="Clínica Piloto", location="Centro")
            db.session.add(default_clinic)
            db.session.commit()
            print("Clínica padrão criada para testes.")
    socketio.run(app, host="0.0.0.0", port=APP_PORT, debug=True, allow_unsafe_werkzeug=True)
