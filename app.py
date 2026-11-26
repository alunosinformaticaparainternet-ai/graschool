from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

import sqlite3
import os

from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

import smtplib
from email.message import EmailMessage
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


# =====================================================
# CONFIGURAÇÃO DO FLASK
# =====================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

app.secret_key = os.environ.get(
    "GRASCHOOL_SECRET_KEY",
    "graschool-chave-local"
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
BANCO_DADOS = os.path.join(BASE_DIR, "banco.db")


# =====================================================
# CONEXÃO COM O BANCO DE DADOS
# =====================================================

def conectar_banco():
    conexao = sqlite3.connect(BANCO_DADOS)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao

# =====================================================
# CONFIGURAÇÃO DE E-MAIL
# =====================================================

SMTP_SERVIDOR = os.environ.get("SMTP_SERVIDOR", "smtp.gmail.com")
SMTP_PORTA = int(os.environ.get("SMTP_PORTA", "587"))
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_SENHA = os.environ.get("SMTP_SENHA", "")

EMAIL_REMETENTE = SMTP_EMAIL

serializador = URLSafeTimedSerializer(app.secret_key)


def gerar_token(email):
    return serializador.dumps(email, salt="graschool-recuperacao-senha")


def verificar_token(token):
    try:
        return serializador.loads(
            token,
            salt="graschool-recuperacao-senha",
            max_age=1800
        )
    except (BadSignature, SignatureExpired):
        return None


def enviar_email_recuperacao(email_destino, link):

    if not SMTP_EMAIL or not SMTP_SENHA:
        raise RuntimeError("Configuração SMTP não encontrada.")

    mensagem = EmailMessage()
    mensagem["Subject"] = "Recuperação de senha - GRASCHOOL"
    mensagem["From"] = EMAIL_REMETENTE
    mensagem["To"] = email_destino

    mensagem.set_content(f"""
Olá!

Recebemos uma solicitação para redefinir sua senha no GRASCHOOL.

Para cadastrar uma nova senha, acesse o link abaixo:

{link}

Este link é válido por 30 minutos.

Se você não solicitou a recuperação, ignore esta mensagem.

Equipe GRASCHOOL
""")

    with smtplib.SMTP(SMTP_SERVIDOR, SMTP_PORTA) as servidor:
        servidor.starttls()
        servidor.login(SMTP_EMAIL, SMTP_SENHA)
        servidor.send_message(mensagem)

# =====================================================
# CRIAÇÃO E ATUALIZAÇÃO DAS TABELAS
# =====================================================

def criar_banco():

    conexao = conectar_banco()
    cursor = conexao.cursor()

    # USUÁRIOS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'aluno',
            data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # DISCIPLINAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disciplinas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            professor TEXT DEFAULT '',
            carga_horaria INTEGER DEFAULT 0,
            periodo TEXT DEFAULT '2026'
        )
    """)

    # NOTAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            disciplina_id INTEGER NOT NULL,
            nota1 REAL DEFAULT 0,
            nota2 REAL DEFAULT 0,
            nota3 REAL DEFAULT 0,
            nota4 REAL DEFAULT 0,
            periodo TEXT DEFAULT '2026',

            FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,

            FOREIGN KEY (disciplina_id)
                REFERENCES disciplinas(id) ON DELETE CASCADE,

            UNIQUE (usuario_id, disciplina_id, periodo)
        )
    """)

    # FREQUÊNCIAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS frequencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            disciplina_id INTEGER NOT NULL,
            total_aulas INTEGER DEFAULT 0,
            presencas INTEGER DEFAULT 0,
            faltas INTEGER DEFAULT 0,
            periodo TEXT DEFAULT '2026',

            FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE CASCADE,

            FOREIGN KEY (disciplina_id)
                REFERENCES disciplinas(id) ON DELETE CASCADE,

            UNIQUE (usuario_id, disciplina_id, periodo)
        )
    """)

    # ANOTAÇÕES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anotacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            conteudo TEXT NOT NULL,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    # ADICIONA A COLUNA MATERIA EM BANCOS EXISTENTES
    colunas_anotacoes = cursor.execute(
        "PRAGMA table_info(anotacoes)"
    ).fetchall()

    nomes_colunas = [
        coluna["name"] for coluna in colunas_anotacoes
    ]

    if "materia" not in nomes_colunas:
        cursor.execute("""
            ALTER TABLE anotacoes
            ADD COLUMN materia TEXT DEFAULT ''
        """)

    # NOTIFICAÇÕES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notificacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            mensagem TEXT NOT NULL,
            lida INTEGER DEFAULT 0,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    # PLANOS DE ENSINO
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS planos_ensino (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disciplina_id INTEGER NOT NULL,
            objetivo TEXT DEFAULT '',
            conteudos TEXT DEFAULT '',
            metodologia TEXT DEFAULT '',
            avaliacao TEXT DEFAULT '',

            FOREIGN KEY (disciplina_id)
                REFERENCES disciplinas(id) ON DELETE CASCADE
        )
    """)

    # DISCIPLINAS INICIAIS
    disciplinas_iniciais = [
        ("Banco de Dados", 80),
        ("UI e UX", 60),
        ("APIs", 60),
        ("Lógica", 80),
        ("Front-End", 100),
        ("Modelagem e Desenvolvimento", 100),
        ("Matemática", 80),
        ("Português", 80),
        ("História", 60),
        ("Informática", 100)
    ]

    for nome, carga_horaria in disciplinas_iniciais:
        cursor.execute("""
            INSERT OR IGNORE INTO disciplinas (
                nome,
                carga_horaria,
                periodo
            )
            VALUES (?, ?, '2026')
        """, (nome, carga_horaria))

    conexao.commit()
    conexao.close()


# =====================================================
# PROTEÇÃO DE ROTAS
# =====================================================

def login_obrigatorio(funcao):

    @wraps(funcao)
    def verificar_login(*args, **kwargs):

        if "usuario_id" not in session:
            flash(
                "Faça login para acessar o sistema.",
                "aviso"
            )

            return redirect(url_for("login"))

        return funcao(*args, **kwargs)

    return verificar_login


# =====================================================
# PÁGINA INICIAL
# =====================================================

@app.route("/")
def index():

    if "usuario_id" in session:
        return redirect(url_for("inicio"))

    return redirect(url_for("login"))


# =====================================================
# CADASTRO
# =====================================================

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():

    if request.method == "POST":

        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not nome or not email or not senha:
            flash("Preencha todos os campos.", "erro")
            return redirect(url_for("cadastro"))

        if len(senha) < 6:
            flash(
                "A senha precisa ter pelo menos 6 caracteres.",
                "erro"
            )
            return redirect(url_for("cadastro"))

        senha_hash = generate_password_hash(senha)
        conexao = conectar_banco()

        try:
            conexao.execute("""
                INSERT INTO usuarios (
                    nome,
                    email,
                    senha,
                    tipo
                )
                VALUES (?, ?, ?, 'aluno')
            """, (nome, email, senha_hash))

            conexao.commit()

            flash(
                "Cadastro realizado! Entre com seu e-mail e senha.",
                "sucesso"
            )

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash(
                "Este e-mail já está cadastrado.",
                "erro"
            )

            return redirect(url_for("cadastro"))

        finally:
            conexao.close()

    return render_template("cadastro.html")


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not email or not senha:
            flash(
                "Informe o e-mail e a senha.",
                "erro"
            )

            return redirect(url_for("login"))

        conexao = conectar_banco()

        try:
            usuario = conexao.execute("""
                SELECT id, nome, email, senha, tipo
                FROM usuarios
                WHERE email = ?
            """, (email,)).fetchone()

        finally:
            conexao.close()

        if usuario and check_password_hash(usuario["senha"], senha):

            session.clear()

            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome"]
            session["usuario_email"] = usuario["email"]
            session["usuario_tipo"] = usuario["tipo"]

            return redirect(url_for("inicio"))

        flash(
            "E-mail ou senha incorretos.",
            "erro"
        )

        return redirect(url_for("login"))

    return render_template("login.html")


# =====================================================
# SAIR
# =====================================================

@app.route("/sair")
def sair():

    session.clear()

    return redirect(url_for("login"))


# =====================================================
# INÍCIO
# =====================================================

@app.route("/inicio")
@login_obrigatorio
def inicio():

    return render_template(
        "inicio.html",
        nome_usuario=session.get("usuario_nome", "Aluno"),
        usuario_nome=session.get("usuario_nome", "Aluno")
    )


# =====================================================
# NOTAS
# =====================================================

@app.route("/notas")
@login_obrigatorio
def notas():

    conexao = conectar_banco()

    try:
        disciplinas = conexao.execute("""
            SELECT
                d.id AS disciplina_id,
                d.nome AS disciplina,
                COALESCE(n.nota1, 0) AS nota1,
                COALESCE(n.nota2, 0) AS nota2,
                COALESCE(n.nota3, 0) AS nota3,
                COALESCE(n.nota4, 0) AS nota4
            FROM disciplinas d

            LEFT JOIN notas n
                ON n.disciplina_id = d.id
                AND n.usuario_id = ?
                AND n.periodo = '2026'

            ORDER BY d.nome
        """, (session["usuario_id"],)).fetchall()

    finally:
        conexao.close()

    return render_template(
        "notas.html",
        disciplinas=disciplinas
    )


@app.route("/salvar_notas", methods=["POST"])
@login_obrigatorio
def salvar_notas():

    usuario_id = session["usuario_id"]
    conexao = conectar_banco()

    try:
        disciplinas = conexao.execute(
            "SELECT id FROM disciplinas"
        ).fetchall()

        for disciplina in disciplinas:

            disciplina_id = disciplina["id"]
            valores = []

            for campo in ("nota1", "nota2", "nota3", "nota4"):

                valor = request.form.get(
                    f"{campo}_{disciplina_id}",
                    "0"
                ).strip().replace(",", ".")

                try:
                    numero = float(valor)

                except ValueError:
                    flash(
                        "Informe notas numéricas válidas.",
                        "erro"
                    )

                    return redirect(url_for("notas"))

                if not 0 <= numero <= 10:
                    flash(
                        "As notas devem estar entre 0 e 10.",
                        "erro"
                    )

                    return redirect(url_for("notas"))

                valores.append(numero)

            conexao.execute("""
                INSERT INTO notas (
                    usuario_id,
                    disciplina_id,
                    nota1,
                    nota2,
                    nota3,
                    nota4,
                    periodo
                )
                VALUES (?, ?, ?, ?, ?, ?, '2026')

                ON CONFLICT (
                    usuario_id,
                    disciplina_id,
                    periodo
                )
                DO UPDATE SET
                    nota1 = excluded.nota1,
                    nota2 = excluded.nota2,
                    nota3 = excluded.nota3,
                    nota4 = excluded.nota4
            """, (
                usuario_id,
                disciplina_id,
                valores[0],
                valores[1],
                valores[2],
                valores[3]
            ))

        conexao.commit()

        flash(
            "Notas salvas com sucesso!",
            "sucesso"
        )

    finally:
        conexao.close()

    return redirect(url_for("notas"))


# =====================================================
# FREQUÊNCIA
# =====================================================

@app.route("/frequencia")
@login_obrigatorio
def frequencia():

    conexao = conectar_banco()

    try:
        registros = conexao.execute("""
            SELECT
                d.id AS disciplina_id,
                d.nome AS disciplina,
                COALESCE(f.total_aulas, 0) AS total_aulas,
                COALESCE(f.presencas, 0) AS presencas,
                COALESCE(f.faltas, 0) AS faltas,
                COALESCE(f.periodo, '2026') AS periodo
            FROM disciplinas d

            LEFT JOIN frequencias f
                ON f.disciplina_id = d.id
                AND f.usuario_id = ?
                AND f.periodo = '2026'

            ORDER BY d.nome
        """, (session["usuario_id"],)).fetchall()

        # Totais do ano
        total_aulas_ano = 0
        total_presencas_ano = 0
        total_faltas_ano = 0

        for registro in registros:
            total_aulas_ano += registro["total_aulas"]
            total_presencas_ano += registro["presencas"]
            total_faltas_ano += registro["faltas"]

        # Como o banco atual só registra o período anual,
        # os bimestres começam sem dados.
        dados_periodos = {
            "ano": {
                "titulo": "Ano Letivo 2026",
                "descricao": "Dados acumulados de todo o ano escolar.",
                "aulas": total_aulas_ano,
                "presencas": total_presencas_ano,
                "faltas": total_faltas_ano
            },
            "bimestre1": {
                "titulo": "1º Bimestre",
                "descricao": "Não há registros específicos deste bimestre.",
                "aulas": 0,
                "presencas": 0,
                "faltas": 0
            },
            "bimestre2": {
                "titulo": "2º Bimestre",
                "descricao": "Não há registros específicos deste bimestre.",
                "aulas": 0,
                "presencas": 0,
                "faltas": 0
            },
            "bimestre3": {
                "titulo": "3º Bimestre",
                "descricao": "Não há registros específicos deste bimestre.",
                "aulas": 0,
                "presencas": 0,
                "faltas": 0
            },
            "bimestre4": {
                "titulo": "4º Bimestre",
                "descricao": "Não há registros específicos deste bimestre.",
                "aulas": 0,
                "presencas": 0,
                "faltas": 0
            }
        }

    finally:
        conexao.close()

    return render_template(
        "frequencia.html",
        frequencias=registros,
        dados_periodos=dados_periodos
    )

# =====================================================
# PERFIL
# =====================================================

@app.route("/perfil")
@login_obrigatorio
def perfil():

    conexao = conectar_banco()

    try:
        usuario = conexao.execute("""
            SELECT id, nome, email, tipo, data_cadastro
            FROM usuarios
            WHERE id = ?
        """, (session["usuario_id"],)).fetchone()

    finally:
        conexao.close()

    return render_template(
        "perfil.html",
        usuario=usuario
    )


# =====================================================
# SERVIÇOS
# =====================================================

@app.route("/servicos")
@login_obrigatorio
def servicos():

    return render_template("servicos.html")

# =====================================================
# ANOTAÇÕES: CADASTRAR, EDITAR E LISTAR
# =====================================================

@app.route("/anotacoes", methods=["GET", "POST"])
@login_obrigatorio
def anotacoes():

    conexao = conectar_banco()

    try:

        if request.method == "POST":

            anotacao_id = request.form.get(
                "anotacao_id", ""
            ).strip()

            titulo = request.form.get(
                "titulo", ""
            ).strip()

            materia = request.form.get(
                "materia", ""
            ).strip()

            conteudo = request.form.get(
                "conteudo", ""
            ).strip()

            usuario_id = session["usuario_id"]

            # VERIFICAR CAMPOS
            if not titulo or not materia or not conteudo:

                flash(
                    "Preencha todos os campos da anotação.",
                    "erro"
                )

                return redirect(url_for("anotacoes"))

            # =========================================
            # EDITAR ANOTAÇÃO EXISTENTE
            # =========================================

            if anotacao_id:

                try:
                    anotacao_id = int(anotacao_id)

                except ValueError:

                    flash(
                        "Identificação da anotação inválida.",
                        "erro"
                    )

                    return redirect(url_for("anotacoes"))

                resultado = conexao.execute("""
                    UPDATE anotacoes

                    SET
                        titulo = ?,
                        materia = ?,
                        conteudo = ?

                    WHERE
                        id = ?
                        AND usuario_id = ?

                """, (
                    titulo,
                    materia,
                    conteudo,
                    anotacao_id,
                    usuario_id
                ))

                conexao.commit()

                if resultado.rowcount > 0:

                    flash(
                        "Anotação editada com sucesso!",
                        "sucesso"
                    )

                else:

                    flash(
                        "Não foi possível encontrar essa anotação.",
                        "erro"
                    )

            # =========================================
            # CADASTRAR NOVA ANOTAÇÃO
            # =========================================

            else:

                conexao.execute("""
                    INSERT INTO anotacoes (
                        usuario_id,
                        titulo,
                        materia,
                        conteudo
                    )

                    VALUES (?, ?, ?, ?)

                """, (
                    usuario_id,
                    titulo,
                    materia,
                    conteudo
                ))

                conexao.commit()

                flash(
                    "Anotação cadastrada com sucesso!",
                    "sucesso"
                )

            return redirect(url_for("anotacoes"))

        # =============================================
        # LISTAR ANOTAÇÕES DO USUÁRIO
        # =============================================

        anotacoes_salvas = conexao.execute("""
            SELECT
                id,
                titulo,
                COALESCE(materia, '') AS materia,
                conteudo,
                data_criacao

            FROM anotacoes

            WHERE usuario_id = ?

            ORDER BY id DESC

        """, (
            session["usuario_id"],
        )).fetchall()

    finally:
        conexao.close()

    return render_template(
        "anotacoes.html",
        anotacoes=anotacoes_salvas
    )
    
# =====================================================
# EXCLUIR ANOTAÇÃO
# =====================================================

@app.route(
    "/excluir_anotacao/<int:anotacao_id>",
    methods=["POST"]
)
@login_obrigatorio
def excluir_anotacao(anotacao_id):

    conexao = conectar_banco()

    try:
        conexao.execute("""
            DELETE FROM anotacoes
            WHERE id = ?
              AND usuario_id = ?
        """, (
            anotacao_id,
            session["usuario_id"]
        ))

        conexao.commit()

        flash(
            "Anotação excluída com sucesso!",
            "sucesso"
        )

    finally:
        conexao.close()

    return redirect(url_for("anotacoes"))

# =====================================================
# ESQUECEU A SENHA
# =====================================================

@app.route("/esqueceu_senha", methods=["GET", "POST"])
def esqueceu_senha():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Informe seu e-mail.", "erro")
            return redirect(url_for("esqueceu_senha"))

        conexao = conectar_banco()

        try:
            usuario = conexao.execute("""
                SELECT id, email
                FROM usuarios
                WHERE email = ?
            """, (email,)).fetchone()

        finally:
            conexao.close()

        # Resposta genérica para não revelar quais e-mails
        # estão cadastrados no sistema.
        if usuario:

            token = gerar_token(usuario["email"])

            link = url_for(
                "redefinir_senha",
                token=token,
                _external=True
            )

            try:
                enviar_email_recuperacao(email, link)

            except Exception:
                app.logger.exception(
                    "Erro ao enviar e-mail de recuperação."
                )

                flash(
                    "Não foi possível enviar o e-mail. Verifique a configuração SMTP.",
                    "erro"
                )

                return redirect(url_for("esqueceu_senha"))

        flash(
            "Se o e-mail estiver cadastrado, você receberá um link de recuperação.",
            "sucesso"
        )

        return redirect(url_for("login"))

    return render_template("esqueceu_senha.html")


# =====================================================
# REDEFINIR SENHA
# =====================================================

@app.route(
    "/redefinir_senha/<token>",
    methods=["GET", "POST"]
)
def redefinir_senha(token):

    email = verificar_token(token)

    if not email:
        flash(
            "O link expirou ou é inválido. Solicite uma nova recuperação.",
            "erro"
        )
        return redirect(url_for("esqueceu_senha"))

    if request.method == "POST":

        senha = request.form.get("senha", "")
        confirmar_senha = request.form.get(
            "confirmar_senha", ""
        )

        if len(senha) < 6:
            flash(
                "A senha precisa ter pelo menos 6 caracteres.",
                "erro"
            )
            return redirect(
                url_for("redefinir_senha", token=token)
            )

        if senha != confirmar_senha:
            flash(
                "As senhas não coincidem.",
                "erro"
            )
            return redirect(
                url_for("redefinir_senha", token=token)
            )

        nova_senha_hash = generate_password_hash(senha)

        conexao = conectar_banco()

        try:
            resultado = conexao.execute("""
                UPDATE usuarios
                SET senha = ?
                WHERE email = ?
            """, (nova_senha_hash, email))

            conexao.commit()

            if resultado.rowcount == 0:
                flash(
                    "Usuário não encontrado.",
                    "erro"
                )
                return redirect(url_for("esqueceu_senha"))

        finally:
            conexao.close()

        flash(
            "Senha alterada com sucesso! Faça login com sua nova senha.",
            "sucesso"
        )

        return redirect(url_for("login"))

    return render_template("redefinir_senha.html")



# =====================================================
# PLANOS DE ENSINO
# =====================================================

@app.route("/planos")
@login_obrigatorio
def planos():

    conexao = conectar_banco()

    try:
        planos_salvos = conexao.execute("""
            SELECT
                d.id AS disciplina_id,
                d.nome AS disciplina,
                d.professor,
                d.carga_horaria,
                p.objetivo,
                p.conteudos,
                p.metodologia,
                p.avaliacao
            FROM disciplinas d

            LEFT JOIN planos_ensino p
                ON p.disciplina_id = d.id

            ORDER BY d.nome
        """).fetchall()

    finally:
        conexao.close()

    return render_template(
        "planos.html",
        planos=planos_salvos
    )


# =====================================================
# DISCIPLINAS
# =====================================================

@app.route("/disciplinas")
@login_obrigatorio
def disciplinas():

    conexao = conectar_banco()

    try:
        disciplinas_salvas = conexao.execute("""
            SELECT
                id,
                nome,
                professor,
                carga_horaria,
                periodo
            FROM disciplinas
            ORDER BY nome
        """).fetchall()

    finally:
        conexao.close()

    return render_template(
        "disciplinas.html",
        disciplinas=disciplinas_salvas
    )


# =====================================================
# NOTIFICAÇÕES
# =====================================================

@app.route("/notificacoes")
@login_obrigatorio
def notificacoes():

    conexao = conectar_banco()

    try:
        notificacoes_salvas = conexao.execute("""
            SELECT
                id,
                titulo,
                mensagem,
                lida,
                data_criacao
            FROM notificacoes
            WHERE usuario_id = ?
            ORDER BY id DESC
        """, (
            session["usuario_id"],
        )).fetchall()

    finally:
        conexao.close()

    return render_template(
        "notificacoes.html",
        notificacoes=notificacoes_salvas
    )


@app.route(
    "/notificacoes/<int:notificacao_id>/ler",
    methods=["POST"]
)
@login_obrigatorio
def ler_notificacao(notificacao_id):

    conexao = conectar_banco()

    try:
        conexao.execute("""
            UPDATE notificacoes
            SET lida = 1
            WHERE id = ?
              AND usuario_id = ?
        """, (
            notificacao_id,
            session["usuario_id"]
        ))

        conexao.commit()

    finally:
        conexao.close()

    return redirect(url_for("notificacoes"))


# =====================================================
# AJUDA
# =====================================================

@app.route("/ajuda")
@login_obrigatorio
def ajuda():

    return render_template("ajuda.html")


# =====================================================
# INTEGRANTES
# =====================================================

@app.route("/integrantes")
def integrantes():

    return render_template("integrantes.html")


# =====================================================
# EXECUÇÃO
# =====================================================

if __name__ == "__main__":

    criar_banco()

    print("=" * 45)
    print("GRASCHOOL iniciado com sucesso!")
    print("Banco de dados:", BANCO_DADOS)
    print("Endereço: http://127.0.0.1:5000")
    print("=" * 45)

    app.run(debug=True)