# --- 1. Importações ---
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import bcrypt
from datetime import date
from collections import defaultdict  # Importação necessária

# --- 2. Configuração Inicial (sem mudanças) ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'minha-chave-secreta-muito-segura-12345'


# --- 3. Função de Conexão (sem mudanças) ---
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD'),
            database=os.environ.get('DB_NAME')
        )
        return conn
    except Error as e:
        print(f"Erro ao conectar ao MySQL: {e}")
        return None


# --- 4. Rotas de Autenticação (sem mudanças) ---
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
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco.', 'danger')
            return render_template('cadastro.html')
        cursor = conn.cursor(dictionary=True)
        try:
            sql_query = "INSERT INTO usuarios (nome, email, hash_senha) VALUES (%s, %s, %s)"
            dados_do_usuario = (nome, email, hash_senha)
            cursor.execute(sql_query, dados_do_usuario)
            conn.commit()
            flash('Cadastro realizado com sucesso! Faça o login.', 'success')
            return redirect(url_for('pagina_login'))
        except Error as e:
            if e.errno == 1062:
                flash('Este email já está cadastrado. Tente outro.', 'danger')
            else:
                flash(f'Erro ao cadastrar: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
    return render_template('cadastro.html')


@app.route('/login', methods=['GET', 'POST'])
def pagina_login():
    if request.method == 'POST':
        email = request.form['email']
        senha_pura_digitada = request.form['senha']
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco.', 'danger')
            return render_template('login.html')
        cursor = conn.cursor(dictionary=True)
        sql_query = "SELECT * FROM usuarios WHERE email = %s"
        cursor.execute(sql_query, (email,))
        usuario = cursor.fetchone()
        if usuario:
            hash_salvo_no_banco = usuario['hash_senha'].encode('utf-8')
            senha_digitada_bytes = senha_pura_digitada.encode('utf-8')
            if bcrypt.checkpw(senha_digitada_bytes, hash_salvo_no_banco):
                session['logado'] = True
                session['usuario_id'] = usuario['id']
                session['usuario_nome'] = usuario['nome']
                cursor.close()
                conn.close()
                return redirect(url_for('pagina_dashboard'))
        cursor.close()
        conn.close()
        flash('Email ou senha incorretos.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def pagina_logout():
    session.clear()
    flash('Você foi desconectado.', 'info')
    return redirect(url_for('pagina_login'))


# --- 5. Rotas de Fichas de Treino ---
@app.route('/dashboard')
def pagina_dashboard():
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))
    conn = get_db_connection()
    if conn is None:
        flash('Erro de conexão com o banco.', 'danger')
        return render_template('dashboard.html', fichas=[])
    cursor = conn.cursor(dictionary=True)
    usuario_id_logado = session['usuario_id']
    sql_query = """
        SELECT 
            ft.*, 
            COUNT(fe.id) AS total_exercicios
        FROM fichas_treino AS ft
        LEFT JOIN ficha_exercicios AS fe ON ft.id = fe.ficha_id
        WHERE ft.usuario_id = %s
        GROUP BY ft.id
        ORDER BY FIELD(ft.dia_semana, 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom')
    """
    cursor.execute(sql_query, (usuario_id_logado,))
    lista_de_fichas = cursor.fetchall()
    cursor.close()
    conn.close()
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
        conn = get_db_connection()
        if conn is None:
            flash('Erro de conexão com o banco.', 'danger')
            return render_template('criar_ficha.html')
        cursor = conn.cursor()
        try:
            sql_query = "INSERT INTO fichas_treino (usuario_id, nome_ficha, dia_semana) VALUES (%s, %s, %s)"
            cursor.execute(sql_query, (usuario_id_logado, nome_ficha, dia_semana))
            conn.commit()
            flash('Ficha de treino criada com sucesso!', 'success')
            return redirect(url_for('pagina_dashboard'))
        except Error as e:
            flash(f'Erro ao criar ficha: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
    return render_template('criar_ficha.html')


# --- 6. Rotas de Detalhe da Ficha e Biblioteca ---
@app.route('/ficha/<int:ficha_id>')
def pagina_detalhe_ficha(ficha_id):
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))
    conn = get_db_connection()
    if conn is None:
        flash('Erro de conexão com o banco.', 'danger')
        return redirect(url_for('pagina_dashboard'))
    cursor = conn.cursor(dictionary=True)
    usuario_id_logado = session['usuario_id']
    sql_ficha = "SELECT * FROM fichas_treino WHERE id = %s AND usuario_id = %s"
    cursor.execute(sql_ficha, (ficha_id, usuario_id_logado))
    ficha = cursor.fetchone()
    if not ficha:
        flash('Ficha de treino não encontrada.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('pagina_dashboard'))
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
    cursor.execute(sql_exercicios, (ficha_id,))
    exercicios_da_ficha = cursor.fetchall()
    cursor.close()
    conn.close()
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
    conn = get_db_connection()
    if conn is None:
        flash('Erro de conexão.', 'danger')
        return redirect(url_for('pagina_detalhe_ficha', ficha_id=ficha_id))
    cursor = conn.cursor(dictionary=True)
    usuario_id_logado = session['usuario_id']
    sql_ficha = "SELECT * FROM fichas_treino WHERE id = %s AND usuario_id = %s"
    cursor.execute(sql_ficha, (ficha_id, usuario_id_logado))
    ficha = cursor.fetchone()
    if not ficha:
        flash('Ficha de treino não encontrada.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('pagina_dashboard'))
    if request.method == 'POST':
        try:
            biblioteca_exercicio_id = request.form['biblioteca_id']
            sql_insert = "INSERT INTO ficha_exercicios (ficha_id, biblioteca_exercicio_id) VALUES (%s, %s)"
            cursor.execute(sql_insert, (ficha_id, biblioteca_exercicio_id))
            conn.commit()
            flash('Exercício adicionado à ficha!', 'success')
        except Error as e:
            if e.errno == 1062:
                flash('Este exercício já está na sua ficha.', 'info')
            else:
                flash(f'Erro ao adicionar: {e}', 'danger')
        return redirect(url_for('pagina_adicionar_exercicio_ficha', ficha_id=ficha_id))
    sql_meus_ids = "SELECT biblioteca_exercicio_id FROM ficha_exercicios WHERE ficha_id = %s"
    cursor.execute(sql_meus_ids, (ficha_id,))
    ids_que_ja_tenho = [item['biblioteca_exercicio_id'] for item in cursor.fetchall()]
    sql_biblioteca = "SELECT * FROM biblioteca_exercicios ORDER BY nome"
    cursor.execute(sql_biblioteca)
    lista_da_biblioteca = cursor.fetchall()
    grupos_musculares = defaultdict(list)
    for exercicio in lista_da_biblioteca:
        grupos_musculares[exercicio['grupo_muscular']].append(exercicio)
    cursor.close()
    conn.close()
    return render_template(
        'biblioteca.html',
        grupos_musculares=grupos_musculares,
        ids_ja_adicionados=ids_que_ja_tenho,
        ficha=ficha
    )


# --- 7. ROTAS DE REGISTO (RELIGADAS) ---

@app.route('/registrar_treino/<int:ficha_exercicio_id>', methods=['GET', 'POST'])
def pagina_registrar_treino(ficha_exercicio_id):
    if 'logado' not in session:
        flash('Você precisa fazer login.', 'warning')
        return redirect(url_for('pagina_login'))

    conn = get_db_connection()
    if conn is None:
        flash('Erro de conexão com o banco.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    cursor = conn.cursor(dictionary=True)
    usuario_id_logado = session['usuario_id']

    # Lidar com o ENVIO (POST)
    if request.method == 'POST':
        peso = request.form['peso']
        reps = request.form['reps']
        data_hoje = date.today()

        try:
            # Insere na nova tabela 'registros_treino'
            sql_insert = """
                INSERT INTO registros_treino (usuario_id, ficha_exercicio_id, data_registro, peso_kg, repeticoes)
                VALUES (%s, %s, %s, %s, %s)
            """
            dados = (usuario_id_logado, ficha_exercicio_id, data_hoje, peso, reps)
            cursor.execute(sql_insert, dados)
            conn.commit()
            flash('Treino registrado com sucesso!', 'success')
        except Error as e:
            flash(f'Erro ao registrar treino: {e}', 'danger')

        # Redireciona de volta para a própria página
        return redirect(url_for('pagina_registrar_treino', ficha_exercicio_id=ficha_exercicio_id))

    # Se for GET (visitando a página)

    # 1. Buscar os dados do exercício (Nome, e ID da Ficha para o botão "Voltar")
    sql_exercicio = """
        SELECT 
            bib.nome,
            fe.ficha_id
        FROM ficha_exercicios AS fe
        JOIN biblioteca_exercicios AS bib ON fe.biblioteca_exercicio_id = bib.id
        JOIN fichas_treino AS ft ON fe.ficha_id = ft.id
        WHERE fe.id = %s AND ft.usuario_id = %s
    """
    cursor.execute(sql_exercicio, (ficha_exercicio_id, usuario_id_logado))
    exercicio = cursor.fetchone()

    if not exercicio:
        flash('Exercício não encontrado ou não pertence a esta ficha.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('pagina_dashboard'))

    # 2. Buscar o HISTÓRICO (da nova tabela 'registros_treino')
    sql_historico = """
        SELECT * FROM registros_treino 
        WHERE ficha_exercicio_id = %s AND usuario_id = %s
        ORDER BY data_registro DESC, id DESC
    """
    cursor.execute(sql_historico, (ficha_exercicio_id, usuario_id_logado))
    lista_de_registros = cursor.fetchall()

    # 3. Calcular Progresso (%) (igual a antes)
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

            # 4. PREPARAR DADOS PARA O GRÁFICO (igual a antes)
    registros_para_grafico = sorted(lista_de_registros, key=lambda r: r['data_registro'])
    scatter_data = []
    for reg in registros_para_grafico:
        scatter_data.append({
            'x': int(reg['repeticoes']),
            'y': float(reg['peso_kg']),
            't': reg['data_registro'].strftime('%d/%m/%Y')
        })

    cursor.close()
    conn.close()

    # 5. Renderizar a página
    return render_template(
        'registrar_treino.html',
        exercicio=exercicio,
        registros=lista_de_registros,
        progresso_info=progresso_info,
        scatter_data=scatter_data,
        ficha_exercicio_id=ficha_exercicio_id  # Passamos o ID do exercício
    )


@app.route('/deletar_registro', methods=['POST'])
def deletar_registro():
    if 'logado' not in session or request.method != 'POST':
        flash('Acesso não permitido.', 'warning')
        return redirect(url_for('pagina_login'))

    try:
        registro_id = request.form['registro_id']
        ficha_exercicio_id = request.form['ficha_exercicio_id']  # Para o redirect
        usuario_id_logado = session['usuario_id']
    except KeyError:
        flash('Erro ao processar formulário.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    conn = get_db_connection()
    if conn is None:
        flash('Erro de conexão com o banco.', 'danger')
        return redirect(url_for('pagina_registrar_treino', ficha_exercicio_id=ficha_exercicio_id))

    cursor = conn.cursor()

    try:
        # Apaga da nova tabela 'registros_treino'
        sql_delete = "DELETE FROM registros_treino WHERE id = %s AND usuario_id = %s"
        dados = (registro_id, usuario_id_logado)
        cursor.execute(sql_delete, dados)
        conn.commit()

        if cursor.rowcount > 0:
            flash('Registro deletado com sucesso!', 'success')
        else:
            flash('Erro: Registro não encontrado.', 'danger')

    except Error as e:
        flash(f'Erro ao deletar: {e}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('pagina_registrar_treino', ficha_exercicio_id=ficha_exercicio_id))


@app.route('/remover_exercicio_da_ficha', methods=['POST'])
def remover_exercicio_da_ficha():
    if 'logado' not in session or request.method != 'POST':
        flash('Acesso não permitido.', 'warning')
        return redirect(url_for('pagina_login'))

    try:
        ficha_exercicio_id = request.form['ficha_exercicio_id']
        ficha_id = request.form['ficha_id']  # Para o redirect
        usuario_id_logado = session['usuario_id']
    except KeyError:
        flash('Erro ao processar formulário.', 'danger')
        return redirect(url_for('pagina_dashboard'))

    conn = get_db_connection()
    if conn is None:
        flash('Erro de conexão com o banco.', 'danger')
        return redirect(url_for('pagina_detalhe_ficha', ficha_id=ficha_id))

    cursor = conn.cursor()

    try:
        # SQL para apagar (com segurança)
        sql_delete = """
            DELETE fe FROM ficha_exercicios AS fe
            JOIN fichas_treino AS ft ON fe.ficha_id = ft.id
            WHERE fe.id = %s AND ft.usuario_id = %s
        """
        dados = (ficha_exercicio_id, usuario_id_logado)
        cursor.execute(sql_delete, dados)
        conn.commit()

        if cursor.rowcount > 0:
            flash('Exercício removido da ficha com sucesso.', 'success')
        else:
            flash('Erro: Exercício não encontrado.', 'danger')

    except Error as e:
        flash(f'Erro ao remover exercício: {e}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('pagina_detalhe_ficha', ficha_id=ficha_id))


# --- 8. Rodar o Aplicativo (sem mudanças) ---
if __name__ == '__main__':
    app.run(debug=True)