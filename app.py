# --- 1. Importações (MUDANÇA AQUI) ---
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
# Trocámos 'mysql.connector' por 'psycopg2'
import psycopg2
from psycopg2 import Error
from dotenv import load_dotenv
import bcrypt
from datetime import date
from collections import defaultdict
from psycopg2.extras import RealDictCursor  # IMPORTANTE: Para simular o dictionary=True do MySQL!

# --- 2. Configuração Inicial (sem mudanças) ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'minha-chave-secreta-muito-segura-12345'


# --- 3. Função de Conexão (NOVA FUNÇÃO para PostgreSQL) ---
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            dbname=os.environ.get('DB_NAME'),  # PostgreSQL usa dbname
            port=os.environ.get('DB_PORT'),
            sslmode='require'  # Necessário para segurança em hospedagem na nuvem
        )
        return conn
    except Error as e:
        print(f"Erro ao conectar ao PostgreSQL: {e}")
        return None


# --- Funções de Ajuda (Para simplificar a troca do SQL) ---
def execute_query(query, params=None, fetch_one=False, commit=False, dict_cursor=False):
    conn = get_db_connection()
    if conn is None:
        return None

    # MUDANÇA: Usamos RealDictCursor para simular o dictionary=True
    cursor = conn.cursor(cursor_factory=RealDictCursor) if dict_cursor else conn.cursor()

    try:
        # MUDANÇA: PostgreSQL não usa %s para substituição, usa %s no psycopg2! (Manteremos como está)
        # Atenção: Manter o %s no código Flask, mas o Psycopg2 trata os %s
        cursor.execute(query, params)

        if commit:
            conn.commit()
            return cursor.rowcount
        elif fetch_one:
            return cursor.fetchone()
        else:
            return cursor.fetchall()
    except Error as e:
        print(f"Erro de Banco de Dados: {e}")
        # MUDANÇA: PostgreSQL tem códigos de erro diferentes
        if "duplicate key" in str(e):
            raise Exception("DUPLICATE_ENTRY")
        raise e
    finally:
        cursor.close()
        conn.close()


# --- 4. Rotas de Autenticação (Adaptadas) ---
@app.route('/')
def pagina_inicial():
    if 'usuario_id' in session:
        return redirect(url_for('pagina_dashboard'))
    return redirect(url_for('pagina_login'))


@app.route('/cadastro', methods=['GET', 'POST'])
def pagina_cadastro():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha_pura = request.form['senha']
        hash_senha = bcrypt.hashpw(senha_pura.encode('utf-8'), bcrypt.gensalt())

        try:
            sql_query = "INSERT INTO usuarios (nome, email, hash_senha) VALUES (%s, %s, %s)"
            execute_query(sql_query, (nome, email, hash_senha), commit=True)

            flash('Cadastro realizado com sucesso! Faça o login.', 'success')
            return redirect(url_for('pagina_login'))

        except Exception as e:
            if str(e) == "DUPLICATE_ENTRY":
                flash('Este email já está cadastrado. Tente outro.', 'danger')
            else:
                flash(f'Erro ao cadastrar: {e}', 'danger')

    return render_template('cadastro.html')


@app.route('/login', methods=['GET', 'POST'])
def pagina_login():
    if request.method == 'POST':
        email = request.form['email']
        senha_pura_digitada = request.form['senha']

        sql_query = "SELECT * FROM usuarios WHERE email = %s"
        usuario = execute_query(sql_query, (email,), fetch_one=True, dict_cursor=True)

        if usuario:
            # MUDANÇA: O Psycopg2 devolve o hash como 'memoryview'. Convertemos para bytes.
            hash_salvo_no_banco = bytes(usuario['hash_senha'])
            senha_digitada_bytes = senha_pura_digitada.encode('utf-8')

            if bcrypt.checkpw(senha_digitada_bytes, hash_salvo_no_banco):
                session['logado'] = True
                session['usuario_id'] = usuario['id']
                session['usuario_nome'] = usuario['nome']
                return redirect(url_for('pagina_dashboard'))

        flash('Email ou senha incorretos.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def pagina_logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('pagina_login'))


# --- ROTAS DE FICHAS DE TREINO (Adaptadas) ---

@app.route('/dashboard')
def pagina_dashboard():
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))

    usuario_id_logado = session['usuario_id']

    # MUDANÇA SQL: Adicionamos o 'CAST' para garantir a contagem correta
    sql_query = """
        SELECT 
            ft.*, 
            COUNT(fe.id)::int AS total_exercicios
        FROM fichas_treino AS ft
        LEFT JOIN ficha_exercicios AS fe ON ft.id = fe.ficha_id
        WHERE ft.usuario_id = %s
        GROUP BY ft.id
        ORDER BY CASE ft.dia_semana 
                WHEN 'Seg' THEN 1 
                WHEN 'Ter' THEN 2 
                WHEN 'Qua' THEN 3 
                WHEN 'Qui' THEN 4 
                WHEN 'Sex' THEN 5 
                WHEN 'Sab' THEN 6 
                WHEN 'Dom' THEN 7 
                ELSE 8 END
    """

    lista_de_fichas = execute_query(sql_query, (usuario_id_logado,), dict_cursor=True)
    if lista_de_fichas is None:
        flash('Erro de conexão com o banco.', 'danger')
        return render_template('dashboard.html', fichas=[])

    return render_template('dashboard.html', fichas=lista_de_fichas)


@app.route('/criar_ficha', methods=['GET', 'POST'])
def pagina_criar_ficha():
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))

    if request.method == 'POST':
        nome_ficha = request.form['nome_ficha']
        dia_semana = request.form['dia_semana']
        usuario_id_logado = session['usuario_id']

        sql_query = "INSERT INTO fichas_treino (usuario_id, nome_ficha, dia_semana) VALUES (%s, %s, %s)"
        try:
            execute_query(sql_query, (usuario_id_logado, nome_ficha, dia_semana), commit=True)
            flash('Ficha de treino criada com sucesso!', 'success')
            return redirect(url_for('pagina_dashboard'))
        except Exception as e:
            flash(f'Erro ao criar ficha: {e}', 'danger')

    return render_template('criar_ficha.html')


@app.route('/ficha/<int:ficha_id>')
def pagina_detalhe_ficha(ficha_id):
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))

    usuario_id_logado = session['usuario_id']

    sql_ficha = "SELECT * FROM fichas_treino WHERE id = %s AND usuario_id = %s"
    ficha = execute_query(sql_ficha, (ficha_id, usuario_id_logado), fetch_one=True, dict_cursor=True)

    if not ficha:
        flash('Ficha de treino não encontrada.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    # MUDANÇA SQL: Adicionado AS ficha_exercicio_id para PostgreSQL
    sql_exercicios = """
        SELECT 
            bib.nome, 
            bib.grupo_muscular,
            fe.id AS ficha_exercicio_id
        FROM ficha_exercicios AS fe
        JOIN biblioteca_exercicios AS bib ON fe.biblioteca_exercicio_id = bib.id
        WHERE fe.ficha_id = %s
        ORDER BY bib.nome
    """
    exercicios_da_ficha = execute_query(sql_exercicios, (ficha_id,), dict_cursor=True)

    return render_template(
        'ficha_detalhe.html',
        ficha=ficha,
        exercicios=exercicios_da_ficha
    )


@app.route('/ficha/<int:ficha_id>/adicionar', methods=['GET', 'POST'])
def pagina_adicionar_exercicio_ficha(ficha_id):
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))

    usuario_id_logado = session['usuario_id']

    sql_ficha = "SELECT * FROM fichas_treino WHERE id = %s AND usuario_id = %s"
    ficha = execute_query(sql_ficha, (ficha_id, usuario_id_logado), fetch_one=True, dict_cursor=True)

    if not ficha:
        flash('Ficha de treino não encontrada.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    if request.method == 'POST':
        biblioteca_exercicio_id = request.form['biblioteca_id']
        sql_insert = "INSERT INTO ficha_exercicios (ficha_id, biblioteca_exercicio_id) VALUES (%s, %s)"
        try:
            execute_query(sql_insert, (ficha_id, biblioteca_exercicio_id), commit=True)
            flash('Exercício adicionado à ficha!', 'success')
        except Exception as e:
            if "DUPLICATE_ENTRY" in str(e):
                flash('Este exercício já está na sua ficha.', 'info')
            else:
                flash(f'Erro ao adicionar: {e}', 'danger')

        return redirect(url_for('pagina_adicionar_exercicio_ficha', ficha_id=ficha_id))

    sql_meus_ids = "SELECT biblioteca_exercicio_id FROM ficha_exercicios WHERE ficha_id = %s"
    ids_que_ja_tenho = [item['biblioteca_exercicio_id'] for item in
                        execute_query(sql_meus_ids, (ficha_id,), dict_cursor=True)]

    sql_biblioteca = "SELECT * FROM biblioteca_exercicios ORDER BY nome"
    lista_da_biblioteca = execute_query(sql_biblioteca, dict_cursor=True)

    grupos_musculares = defaultdict(list)
    for exercicio in lista_da_biblioteca:
        grupos_musculares[exercicio['grupo_muscular']].append(exercicio)

    return render_template(
        'biblioteca.html',
        grupos_musculares=grupos_musculares,
        ids_ja_adicionados=ids_que_ja_tenho,
        ficha=ficha
    )


@app.route('/registrar_treino/<int:ficha_exercicio_id>', methods=['GET', 'POST'])
def pagina_registrar_treino(ficha_exercicio_id):
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))

    usuario_id_logado = session['usuario_id']

    # Lidar com o ENVIO (POST)
    if request.method == 'POST':
        peso = request.form['peso']
        reps = request.form['reps']
        data_hoje = date.today()

        sql_insert = """
            INSERT INTO registros_treino (usuario_id, ficha_exercicio_id, data_registro, peso_kg, repeticoes)
            VALUES (%s, %s, %s, %s, %s)
        """
        try:
            execute_query(sql_insert, (usuario_id_logado, ficha_exercicio_id, data_hoje, peso, reps), commit=True)
            flash('Treino registrado com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao registrar treino: {e}', 'danger')

        return redirect(url_for('pagina_registrar_treino', ficha_exercicio_id=ficha_exercicio_id))

    # Se for GET (visitando a página)

    sql_exercicio = """
        SELECT 
            bib.nome,
            fe.ficha_id
        FROM ficha_exercicios AS fe
        JOIN biblioteca_exercicios AS bib ON fe.biblioteca_exercicio_id = bib.id
        JOIN fichas_treino AS ft ON fe.ficha_id = ft.id
        WHERE fe.id = %s AND ft.usuario_id = %s
    """
    exercicio = execute_query(sql_exercicio, (ficha_exercicio_id, usuario_id_logado), fetch_one=True, dict_cursor=True)

    if not exercicio:
        flash('Exercício não encontrado ou não pertence a esta ficha.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    # Buscar o HISTÓRICO (da nova tabela 'registros_treino')
    sql_historico = """
        SELECT * FROM registros_treino 
        WHERE ficha_exercicio_id = %s AND usuario_id = %s
        ORDER BY data_registro DESC, id DESC
    """
    lista_de_registros = execute_query(sql_historico, (ficha_exercicio_id, usuario_id_logado), dict_cursor=True)

    # Calcular Progresso (%)
    progresso_info = None
    if len(lista_de_registros) >= 2:
        try:
            ultimo_peso = lista_de_registros[0]['peso_kg']
            penultimo_peso = lista_de_registros[1]['peso_kg']
            if penultimo_peso > 0:
                percentual = ((ultimo_peso - penultimo_peso) / penultimo_peso) * 100
                progresso_info = {'percentual': round(percentual, 2),
                                  'diferenca': round(ultimo_peso - penultimo_peso, 2)}
        except Exception:
            pass

            # PREPARAR DADOS PARA O GRÁFICO
    registros_para_grafico = sorted(lista_de_registros, key=lambda r: r['data_registro'])
    scatter_data = []
    for reg in registros_para_grafico:
        scatter_data.append({
            'x': int(reg['repeticoes']),
            'y': float(reg['peso_kg']),
            't': reg['data_registro'].strftime('%d/%m/%Y')
        })

    return render_template(
        'registrar_treino.html',
        exercicio=exercicio,
        registros=lista_de_registros,
        progresso_info=progresso_info,
        scatter_data=scatter_data,
        ficha_exercicio_id=ficha_exercicio_id
    )


@app.route('/deletar_registro', methods=['POST'])
def deletar_registro():
    if 'logado' not in session or request.method != 'POST':
        flash('Acesso não permitido.', 'warning')
        return redirect(url_for('pagina_login'))

    try:
        registro_id = request.form['registro_id']
        ficha_exercicio_id = request.form['ficha_exercicio_id']
        usuario_id_logado = session['usuario_id']
    except KeyError:
        flash('Erro ao processar formulário.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    sql_delete = "DELETE FROM registros_treino WHERE id = %s AND usuario_id = %s"
    row_count = execute_query(sql_delete, (registro_id, usuario_id_logado), commit=True)

    if row_count is not None and row_count > 0:
        flash('Registro deletado com sucesso!', 'success')
    else:
        flash('Erro: Registro não encontrado.', 'danger')

    return redirect(url_for('pagina_registrar_treino', ficha_exercicio_id=ficha_exercicio_id))


@app.route('/remover_exercicio_da_ficha', methods=['POST'])
def remover_exercicio_da_ficha():
    if 'logado' not in session or request.method != 'POST':
        flash('Acesso não permitido.', 'warning')
        return redirect(url_for('pagina_login'))

    try:
        ficha_exercicio_id = request.form['ficha_exercicio_id']
        ficha_id = request.form['ficha_id']
        usuario_id_logado = session['usuario_id']
    except KeyError:
        flash('Erro ao processar formulário.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    sql_delete = """
        DELETE fe FROM ficha_exercicios AS fe
        JOIN fichas_treino AS ft ON fe.ficha_id = ft.id
        WHERE fe.id = %s AND ft.usuario_id = %s
    """
    row_count = execute_query(sql_delete, (ficha_exercicio_id, usuario_id_logado), commit=True)

    if row_count is not None and row_count > 0:
        flash('Exercício removido da ficha com sucesso.', 'success')
    else:
        flash('Erro: Exercício não encontrado.', 'danger')

    return redirect(url_for('pagina_detalhe_ficha', ficha_id=ficha_id))


if __name__ == '__main__':
    app.run(debug=True)