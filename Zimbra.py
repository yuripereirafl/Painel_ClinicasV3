import smtplib
from typing import List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re


class zimbra:
    def __init__(self, lista = None):
        self.lista = lista
        self.smtp_server = 'zimbramail.penso.com.br'
        self.smtp_port = 465
        self.username = 'lab.central@centraldeconsultas.med.br'
        self.password = '@CCentral25!'
    
    def enviar_mens(self, recipient: str, subject: str, html_content: str):
        recipients = self.verify_recipient(recipient)
        msg = MIMEMultipart()
        msg['From'] = self.username
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(html_content, 'html'))

        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.username, self.password)
                server.send_message(msg, from_addr=self.username, to_addrs=recipients)
            print(f"E-mail enviado para {recipients}")
            return True
        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
        return False

    def enviar_com_anexo(self, recipient: str, subject: str, html_content: str, attachment_content: bytes, attachment_filename: str):
        from email.mime.base import MIMEBase
        from email import encoders

        recipients = self.verify_recipient(recipient)
        msg = MIMEMultipart()
        msg['From'] = self.username
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject
        msg.attach(MIMEText(html_content, 'html'))

        # Configura o anexo
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment_content)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{attachment_filename}"')
        msg.attach(part)

        try:
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.username, self.password)
                server.send_message(msg, from_addr=self.username, to_addrs=recipients)
            print(f"E-mail enviado com anexo para {recipients}")
            return True
        except Exception as e:
            print(f"Erro ao enviar e-mail com anexo: {e}")
        return False

    def verify_recipient(self, recipient: str) -> list:
        if not recipient:
            return ['yuri.flores@centraldeconsultas.med.br']
        # Separa pelos delimitadores ; ou ,
        recipients = [email.strip() for email in recipient.replace(";", ",").split(",") if email.strip()]
        return recipients

class templates:
    @staticmethod
    def bvd(user: str, senha_temporaria: str) -> str:
        html_content = """
        <!DOCTYPE html>
            <html lang="pt-br">
            <head>
            <meta charset="UTF-8" />
            <title>Seja bem-vindo(a)!</title>
            <style>
                body {
                margin: 0;
                padding: 0;
                background-color: #f5f7fa;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                color: #333333;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
                }

                .email-container {
                max-width: 560px;
                margin: 40px auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1);
                overflow: hidden;
                padding-bottom: 32px;
                border: 1px solid #ddd;
                }

                .header {
                background-color: #144179;
                text-align: center;
                padding: 24px 20px;
                }

                .header img {
                max-width: 240px;
                height: auto;
                display: inline-block;
                }

                .content {
                padding: 32px 40px 0 40px;
                }

                .content h2 {
                color: #144179;
                margin-top: 0;
                margin-bottom: 32px;
                font-weight: 700;
                font-size: 28px;
                line-height: 1.2;
                }

                .field-label {
                font-weight: 600;
                margin-bottom: 8px;
                display: block;
                color: #3567b0;
                font-size: 15px;
                }

                .field-box {
                background-color: #f5f7fa;
                border: 1.8px solid #3567b0;
                border-radius: 8px;
                padding: 14px 20px;
                font-size: 18px;
                color: #144179;
                margin-bottom: 28px;
                user-select: text;
                word-break: break-word;
                box-shadow: inset 0 2px 6px rgba(53, 103, 176, 0.1);
                transition: border-color 0.3s ease;
                }

                .field-box:hover {
                border-color: #fcca32;
                }

                .support {
                margin-top: 12px;
                font-size: 16px;
                color: #333333;
                line-height: 1.5;
                text-align: center;
                }

                .support a {
                color: #144179;
                font-weight: 600;
                text-decoration: underline;
                transition: color 0.2s ease;
                }

                .support a:hover {
                color: #fcca32;
                }

                .footer {
                font-size: 13px;
                color: #999999;
                text-align: center;
                padding: 28px 20px 12px 20px;
                border-top: 1px solid #eee;
                font-style: italic;
                }

                @media screen and (max-width: 600px) {
                .email-container {
                    margin: 20px 10px;
                    padding-bottom: 24px;
                }

                .content {
                    padding: 24px 20px 0 20px;
                }

                .content h2 {
                    font-size: 24px;
                }

                .field-box {
                    font-size: 16px;
                    padding: 12px 14px;
                }

                .support {
                    font-size: 14px;
                }

                .footer {
                    font-size: 12px;
                    padding: 20px 10px 10px 10px;
                }
                }
            </style>
            </head>
            <body>
            <div class="email-container">
                <!-- Cabeçalho -->
                <div class="header">
                <img src="https://centraldeconsultas.med.br/wp-content/uploads/2023/07/Logo-estendido-branco.png" alt="Central de Consultas" />
                </div>

                <!-- Conteúdo -->
                <div class="content">
                <h2>Seja bem-vindo(a)!</h2>

                <label class="field-label" for="usuario">Usuário:</label>
                <div class="field-box" id="usuario">{{USUARIO}}</div>

                <label class="field-label" for="senha">Senha Temporária:</label>
                <div class="field-box" id="senha">{{SENHA_TEMPORARIA}}</div>

                <p class="support">
                    Se precisar de ajuda, entre em contato com nosso suporte: 
                    <a href="mailto:sistemas@centraldeconsultas.med.br">sistemas@centraldeconsultas.med.br</a>
                </p>
                </div>

                <!-- Rodapé -->
                <div class="footer">
                Este é um e-mail automático. Por favor, não responda.
                </div>
            </div>
            </body>
            </html>

        """
        html_content = html_content.replace("{{USUARIO}}", user)
        html_content = html_content.replace("{{SENHA_TEMPORARIA}}", senha_temporaria)
        return html_content
    @staticmethod
    def rpw(senha_temporaria: str) -> str:
        html_content = """
        <!DOCTYPE html>
            <html lang="pt-br">
            <head>
            <meta charset="UTF-8" />
            <title>Recuperação de Senha</title>
            </head>
            <body style="margin: 0; padding: 0; background-color: #f5f7fa; font-family: Arial, sans-serif; color: #333333;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f7fa; padding: 20px 0;">
                <tr>
                <td align="center">
                    <table width="520" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    
                    <!-- Cabeçalho -->
                    <tr>
                        <td style="background-color: #144179; text-align: center; padding: 20px;">
                        <img src="https://centraldeconsultas.med.br/wp-content/uploads/2023/07/Logo-estendido-branco.png" alt="Central de Consultas" style="max-width: 250px;" />
                        </td>
                    </tr>

                    <!-- Conteúdo -->
                    <tr>
                        <td style="padding: 30px;">
                        <h2 style="color: #144179; margin-top: 0;">Recuperação de Senha</h2>
                        <p>Olá,</p>
                        <p>Recebemos uma solicitação para redefinir sua senha.</p>

                        <!-- Box com ícone e texto -->
                        <table cellpadding="0" cellspacing="0" width="100%" style="margin: 20px 0;">
                            <tr>
                            <td style="background-color: #58aadf; color: #ffffff; border-radius: 6px; padding: 12px 16px; font-size: 15px;">
                                <img src="https://cdn-icons-png.flaticon.com/512/3064/3064197.png" width="20" height="20" alt="Ícone de cadeado" style="vertical-align: middle; margin-right: 10px;">
                                Uma <strong>senha temporária</strong> foi gerada para você:
                            </td>
                            </tr>
                        </table>

                        <!-- Senha Temporária -->
                        <table cellpadding="0" cellspacing="0" width="100%">
                            <tr>
                            <td align="center" style="background-color: #fcc361; color: #144179; font-size: 20px; font-weight: bold; padding: 12px; border-radius: 6px; letter-spacing: 1px;">
                                {{temp_pass}}
                            </td>
                            </tr>
                        </table>

                        <!-- Informações -->
                        <ul style="padding-left: 20px; margin-top: 20px;">
                            <li>Essa senha é válida para o seu próximo acesso.</li>
                        </ul>

                        <p>Se você não solicitou essa alteração, apenas ignore esta mensagem.</p>

                        <!-- Contato do Suporte -->
                        <div style="text-align: center; margin-top: 40px; margin-bottom: 20px; font-size: 14px; color: #333333; border-bottom: 1px solid #ccc; padding-bottom: 15px;">
                            <p style="margin: 0;">Se precisar de ajuda, entre em contato com nosso suporte.</p>
                            <p style="margin: 5px 0 0 0;">
                            <a href="mailto:sistemas@centraldeconsultas.med.br" style="color: #144179; text-decoration: none;">sistemas@centraldeconsultas.med.br</a>
                            </p>
                        </div>
                        </td>
                    </tr>

                    <!-- Rodapé -->
                    <tr>
                        <td align="center" style="font-size: 12px; color: #888888; padding: 20px;">
                        Este é um e-mail automático. Por favor, não responda.
                        </td>
                    </tr>
                    </table>
                </td>
                </tr>
            </table>
            </body>
            </html>

        """
        html_content = html_content.replace("{{temp_pass}}", senha_temporaria)
        return html_content
    @staticmethod
    def aue(nome: str, usuario: str, senha: str) -> str:
        html_content = """
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
        <meta charset="UTF-8" />
        <title>Conta Ativada com Sucesso!</title>
        <style>
            body {
            margin: 0;
            padding: 0;
            background-color: #f5f7fa;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #333333;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            }

            .email-container {
            max-width: 560px;
            margin: 40px auto;
            background-color: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1);
            overflow: hidden;
            padding-bottom: 32px;
            border: 1px solid #ddd;
            }

            .header {
            background-color: #144179;
            text-align: center;
            padding: 24px 20px;
            }

            .header img {
            max-width: 240px;
            height: auto;
            display: inline-block;
            }

            .content {
            padding: 32px 40px 0 40px;
            }

            .content h2 {
            color: #144179;
            margin-top: 0;
            margin-bottom: 32px;
            font-weight: 700;
            font-size: 28px;
            line-height: 1.2;
            text-align: center;
            }

            .success-message {
            background-color: #d4edda;
            border: 1.8px solid #28a745;
            border-radius: 8px;
            padding: 20px;
            font-size: 16px;
            color: #155724;
            margin-bottom: 32px;
            text-align: center;
            box-shadow: inset 0 2px 6px rgba(40, 167, 69, 0.1);
            }

            .field-label {
            font-weight: 600;
            margin-bottom: 8px;
            display: block;
            color: #3567b0;
            font-size: 15px;
            }

            .field-box {
            background-color: #f5f7fa;
            border: 1.8px solid #3567b0;
            border-radius: 8px;
            padding: 14px 20px;
            font-size: 18px;
            color: #144179;
            margin-bottom: 28px;
            user-select: text;
            word-break: break-word;
            box-shadow: inset 0 2px 6px rgba(53, 103, 176, 0.1);
            transition: border-color 0.3s ease;
            }

            .field-box:hover {
            border-color: #fcca32;
            }

            .next-steps {
            background-color: #e8f4fd;
            border: 1.8px solid #144179;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 28px;
            }

            .next-steps h3 {
            color: #144179;
            margin-top: 0;
            margin-bottom: 16px;
            font-size: 18px;
            }

            .next-steps p {
            margin-bottom: 12px;
            line-height: 1.5;
            }

            .support {
            margin-top: 12px;
            font-size: 16px;
            color: #333333;
            line-height: 1.5;
            text-align: center;
            }

            .support a {
            color: #144179;
            font-weight: 600;
            text-decoration: underline;
            transition: color 0.2s ease;
            }

            .support a:hover {
            color: #fcca32;
            }

            .footer {
            font-size: 13px;
            color: #999999;
            text-align: center;
            padding: 28px 20px 12px 20px;
            border-top: 1px solid #eee;
            font-style: italic;
            }

            @media screen and (max-width: 600px) {
            .email-container {
                margin: 20px 10px;
                padding-bottom: 24px;
            }

            .content {
                padding: 24px 20px 0 20px;
            }

            .content h2 {
                font-size: 24px;
            }

            .field-box {
                font-size: 16px;
                padding: 12px 14px;
            }

            .success-message {
                padding: 16px;
                font-size: 14px;
            }

            .next-steps {
                padding: 16px;
            }

            .support {
                font-size: 14px;
            }

            .footer {
                font-size: 12px;
                padding: 20px 10px 10px 10px;
            }
            }
        </style>
        </head>
        <body>
        <div class="email-container">
            <!-- Cabeçalho -->
            <div class="header">
            <img src="https://centraldeconsultas.med.br/wp-content/uploads/2023/07/Logo-estendido-branco.png" alt="Central de Consultas" />
            </div>

            <!-- Conteúdo -->
            <div class="content">
            <h2>🎉 Conta Ativada com Sucesso!</h2>

            <div class="success-message">
                <strong>Parabéns, {{NOME_USUARIO}}!</strong><br>
                Sua conta foi ativada com sucesso e você já pode acessar todos os recursos da Central de Consultas.
            </div>

            <label class="field-label" for="usuario">Seu usuário:</label>
            <div class="field-box" id="usuario">{{USUARIO}}</div>

            <label class="field-label" for="data-ativacao">Senha Temporária:</label>
            <div class="field-box" id="data-ativacao">{{SENHA_TEMPORARIA}}</div>

            <div class="next-steps">
                <h3>📋 Próximos passos:</h3>
                <p>• Faça login na plataforma com suas credenciais</p>
                <p>• Complete seu perfil com suas informações pessoais</p>
                <p>• Explore os recursos disponíveis em sua conta</p>
            </div>

            <p class="support">
                Se precisar de ajuda, entre em contato com nosso suporte: 
                <a href="mailto:suporte@centraldeconsultas.med.br">suporte@centraldeconsultas.med.br</a>
            </p>
            </div>

            <!-- Rodapé -->
            <div>
            <body>
            <html>"""
        html_content = html_content.replace("{{NOME_USUARIO}}", nome)
        html_content = html_content.replace("{{USUARIO}}", usuario)
        html_content = html_content.replace("{{SENHA_TEMPORARIA}}", senha)
        return html_content