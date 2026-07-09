from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_socketio import SocketIO, emit, join_room
from models import db, Password, Clinic, Attendant
from datetime import datetime
import pytz
from gtts import gTTS
import os
import time
import glob
import threading
from escpos.printer import Network
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

SAO_PAULO = pytz.timezone('America/Sao_Paulo')

# Lock para evitar que múltiplas threads tentem imprimir ao mesmo tempo
# e sobrescrevam o arquivo temp_ticket.png simultaneamente.
print_lock = threading.Lock()

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
        'id': p.id
    } for p in passwords])

@app.route('/api/clinic/<int:clinic_id>/called_today')
def get_called_today(clinic_id):
    """Retorna as últimas senhas chamadas hoje para a clínica."""
    today = datetime.now(SAO_PAULO).date()
    passwords = Password.query.filter_by(
        clinic_id=clinic_id,
        date=today,
        status='CHAMADO'
    ).order_by(Password.called_at.desc()).limit(10).all()
    
    queue_tags = {'NORMAL': 'N', 'PRIORITARIA': 'P', 'DR_CENTRAL': 'D', 'ODONTO': 'O'}
    
    return jsonify([{
        'number': f"{queue_tags.get(p.queue_type, 'N')}{p.number:02d}",
        'queue_type': p.queue_type,
        'guiche': p.guiche,
        'called_at': p.called_at.strftime('%H:%M:%S') if p.called_at else ''
    } for p in passwords])

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
    # Busca a próxima senha aguardando com o menor ID (ordem de chegada rigorosa)
    next_password = Password.query.filter_by(
        clinic_id=clinic_id, 
        status='AGUARDANDO',
        date=today
    ).order_by(Password.id.asc()).first()

    if next_password:
        next_password.status = 'CHAMADO'
        next_password.guiche = guiche
        next_password.called_at = datetime.now(SAO_PAULO)
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
        emit('no_passwords', {'queue_type': 'TODAS'}, room=request.sid)

@socketio.on('call_next')
def call_next(data):
    """Atendente chama a próxima senha de uma determinada fila."""
    clinic_id = data.get('clinic_id')
    guiche = data.get('guiche')
    queue_type = data.get('queue_type')

    if not clinic_id or not guiche or not queue_type:
        return

    # Busca a próxima senha aguardando para este tipo de fila
    today = datetime.now(SAO_PAULO).date()
    next_password = Password.query.filter_by(
        clinic_id=clinic_id, 
        queue_type=queue_type, 
        status='AGUARDANDO',
        date=today
    ).order_by(Password.id.asc()).first()

    if next_password:
        next_password.status = 'CHAMADO'
        next_password.guiche = guiche
        next_password.called_at = datetime.now(SAO_PAULO)
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
        # Cria uma clínica padrão se não houver nenhuma
        if not Clinic.query.first():
            default_clinic = Clinic(name="Clínica Piloto", location="Centro")
            db.session.add(default_clinic)
            db.session.commit()
            print("Clínica padrão criada para testes.")
    socketio.run(app, host="0.0.0.0", port=APP_PORT, debug=True, allow_unsafe_werkzeug=True)
