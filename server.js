// 1. IMPORTAÇÕES E CONFIGURAÇÃO
require('dotenv').config(); // Tenta carregar .env se existir
const express = require('express');
const mysql = require('mysql2/promise');
const session = require('express-session');
const bcrypt = require('bcryptjs');
const path = require('path');
const cors = require('cors'); // Adicionado para evitar erros de CORS se rodar separado
const fs = require('fs'); // Para verificar se o arquivo existe

// 2. CONFIGURAÇÃO BÁSICA
const app = express();
const PORT = process.env.PORT || 5000; // Porta 5000 para bater com o frontend atual

app.use(cors()); // Habilita CORS
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// Log de requisições (Para você ver no terminal o que está chegando)
app.use((req, res, next) => {
    console.log(`📡 Recebido: ${req.method} ${req.url}`);
    next();
});

// Configuração da Sessão
app.use(session({
    secret: process.env.SECRET_KEY || 'segredo_padrao_cleberfit', // Fallback se não tiver .env
    resave: false,
    saveUninitialized: false,
    cookie: { maxAge: 1000 * 60 * 60 * 24, secure: false } // 24 horas
}));

// 3. CONFIGURAÇÃO DO BANCO DE DADOS (MySQL)
const dbConfig = {
    host: process.env.DB_HOST || 'localhost',
    user: process.env.DB_USER || 'root',
    password: process.env.DB_PASSWORD || 'Iza290623@', // Coloque sua senha aqui se tiver
    database: process.env.DB_NAME || 'diario_de_carga', // Nome do banco novo
    waitForConnections: true,
    connectionLimit: 10,
};

const pool = mysql.createPool(dbConfig);

// 4. FUNÇÃO AUXILIAR PARA O BANCO DE DADOS
async function executeQuery(query, params = []) {
    let connection;
    try {
        connection = await pool.getConnection();
        const [rows] = await connection.execute(query, params);
        return rows;
    } catch (error) {
        if (error.errno === 1062) {
            throw new Error("DUPLICATE_ENTRY");
        }
        console.error('❌ Erro na query SQL:', error);
        throw error;
    } finally {
        if (connection) connection.release();
    }
}

// 5. ROTAS DE AUTENTICAÇÃO

// Login
app.post('/api/login', async (req, res) => {
    const { email, senha } = req.body;
    if (!email || !senha) return res.status(400).json({ success: false, message: 'Dados incompletos.' });

    try {
        // SQL Adaptado: 'senha_hash' é o nome da coluna no novo banco
        const sql = "SELECT id, nome, senha_hash FROM usuarios WHERE email = ?";
        const usuarios = await executeQuery(sql, [email]);
        const usuario = usuarios[0];

        if (!usuario || !(await bcrypt.compare(senha, usuario.senha_hash))) {
            return res.status(401).json({ success: false, message: 'Credenciais inválidas.' });
        }

        req.session.usuario_id = usuario.id;
        req.session.usuario_nome = usuario.nome;
        req.session.logado = true;

        res.json({ success: true, user: { nome: usuario.nome, email }, message: 'Logado!' });
    } catch (error) {
        res.status(500).json({ success: false, message: 'Erro no servidor.' });
    }
});

// Cadastro
app.post('/api/cadastro', async (req, res) => {
    const { nome, email, senha } = req.body;
    if (!nome || !email || !senha) return res.status(400).json({ success: false, message: 'Dados incompletos.' });

    try {
        const salt = await bcrypt.genSalt(10);
        const hash = await bcrypt.hash(senha, salt);

        // SQL Adaptado para tabela 'usuarios'
        await executeQuery("INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)", [nome, email, hash]);
        res.json({ success: true, message: 'Cadastro realizado!' });
    } catch (error) {
        if (error.message === "DUPLICATE_ENTRY") {
            return res.status(409).json({ success: false, message: 'Email já existe.' });
        }
        res.status(500).json({ success: false, message: 'Erro ao cadastrar.' });
    }
});

// Logout
app.get('/api/logout', (req, res) => {
    req.session.destroy(() => res.json({ success: true }));
});

// Middleware de verificação de login para as rotas abaixo
// (Opcional: Se quiser testar sem login, comente as linhas dentro da função)
const requireAuth = (req, res, next) => {
    if (!req.session.logado && !req.query.email) { // Aceita email na query para testar sem session se precisar
        // return res.status(401).json({ success: false, message: 'Não autorizado' });
    }
    next();
};

// ==================================================================
// ROTAS DE DADOS (FICHAS, EXERCÍCIOS, HISTÓRICO)
// ==================================================================

// 1. FICHAS
app.get('/api/fichas', requireAuth, async (req, res) => {
    const email = req.query.email; // Pega email da query se session falhar ou para front SPA
    const userId = req.session.usuario_id;

    try {
        let idParaBusca = userId;
        
        // Fallback: Se não tem session, tenta buscar ID pelo email (para o frontend SPA funcionar liso)
        if (!idParaBusca && email) {
            const users = await executeQuery("SELECT id FROM usuarios WHERE email = ?", [email]);
            if (users.length > 0) idParaBusca = users[0].id;
        }

        if (!idParaBusca) return res.json([]);

        // SQL Adaptado: Coluna 'nome' e 'dia_semana' na tabela 'fichas'
        const sql = "SELECT id, nome, dia_semana FROM fichas WHERE usuario_id = ?";
        const fichas = await executeQuery(sql, [idParaBusca]);
        
        // Mapeia para o frontend (que espera 'dia_semana' ou 'dia')
        const resultado = fichas.map(f => ({ ...f, dia: f.dia_semana }));
        res.json(resultado);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/fichas', requireAuth, async (req, res) => {
    const { user_email, nome, dia } = req.body;
    try {
        // Busca ID
        const users = await executeQuery("SELECT id FROM usuarios WHERE email = ?", [user_email]);
        if (!users.length) return res.status(404).json({ error: "Usuário não encontrado" });

        const sql = "INSERT INTO fichas (usuario_id, nome, dia_semana) VALUES (?, ?, ?)";
        const result = await executeQuery(sql, [users[0].id, nome, dia]);
        res.json({ success: true, id: result.insertId });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.delete('/api/fichas/:id', requireAuth, async (req, res) => {
    await executeQuery("DELETE FROM fichas WHERE id = ?", [req.params.id]);
    res.json({ success: true });
});

// 2. EXERCÍCIOS DA FICHA
app.get('/api/exercicios', requireAuth, async (req, res) => {
    const { ficha_id } = req.query;
    try {
        // SQL Adaptado: 'ficha_exercicios' agora tem 'setup_notes' e 'is_biset'
        const sql = "SELECT * FROM ficha_exercicios WHERE ficha_id = ? ORDER BY ordem ASC, id ASC";
        const rows = await executeQuery(sql, [ficha_id]);
        
        // Adapta para o frontend
        const exercicios = rows.map(ex => ({
            id: ex.id,
            ficha_id: ex.ficha_id,
            nome_exercicio: ex.nome_exercicio, // Frontend antigo esperava 'nome', novo espera 'nome_exercicio' ou adapta
            grupo_muscular: ex.grupo_muscular,
            setup_notes: ex.setup_notes,
            is_biset: ex.is_biset
        }));
        res.json(exercicios);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/exercicios', requireAuth, async (req, res) => {
    const { ficha_id, nome, grupo } = req.body;
    // SQL Adaptado: Insere direto na tabela ficha_exercicios
    const sql = "INSERT INTO ficha_exercicios (ficha_id, nome_exercicio, grupo_muscular, is_biset) VALUES (?, ?, ?, ?)";
    await executeQuery(sql, [ficha_id, nome, grupo, false]);
    res.json({ success: true });
});

app.put('/api/exercicios/:id', requireAuth, async (req, res) => {
    const { notes, is_biset } = req.body;
    const sql = "UPDATE ficha_exercicios SET setup_notes = ?, is_biset = ? WHERE id = ?";
    await executeQuery(sql, [notes, is_biset, req.params.id]);
    res.json({ success: true });
});

app.delete('/api/exercicios/:id', requireAuth, async (req, res) => {
    await executeQuery("DELETE FROM ficha_exercicios WHERE id = ?", [req.params.id]);
    res.json({ success: true });
});

// 3. HISTÓRICO DE TREINOS (Específico ou Geral)
app.get('/api/historico', requireAuth, async (req, res) => {
    const { exercicio_id, email } = req.query;
    
    try {
        if (exercicio_id) {
            // Histórico de UM exercício (Gráfico)
            const sql = "SELECT * FROM historico_treinos WHERE ficha_exercicio_id = ? ORDER BY data_registro DESC";
            const rows = await executeQuery(sql, [exercicio_id]);
            res.json(rows);
        } else if (email) {
            // Histórico GERAL (Calendário / Heatmap)
            const users = await executeQuery("SELECT id FROM usuarios WHERE email = ?", [email]);
            if (!users.length) return res.json([]);

            // Join complexo para pegar o nome do exercício através das tabelas
            const sql = `
                SELECT h.*, fe.nome_exercicio 
                FROM historico_treinos h
                JOIN ficha_exercicios fe ON h.ficha_exercicio_id = fe.id
                JOIN fichas f ON fe.ficha_id = f.id
                WHERE f.usuario_id = ?
                ORDER BY h.data_registro DESC
            `;
            const rows = await executeQuery(sql, [users[0].id]);
            res.json(rows);
        } else {
            res.json([]);
        }
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/historico', requireAuth, async (req, res) => {
    const { ficha_exercicio_id, peso, reps, tipo, data_registro } = req.body;
    // SQL Adaptado: tabela 'historico_treinos'
    const sql = "INSERT INTO historico_treinos (ficha_exercicio_id, peso, repeticoes, tipo_serie, data_registro) VALUES (?, ?, ?, ?, ?)";
    await executeQuery(sql, [ficha_exercicio_id, peso, reps, tipo, data_registro]);
    res.json({ success: true });
});

// 4. PESO CORPORAL (Novo)
app.get('/api/peso', requireAuth, async (req, res) => {
    const { email } = req.query;
    const users = await executeQuery("SELECT id FROM usuarios WHERE email = ?", [email]);
    if (!users.length) return res.json([]);

    const sql = "SELECT * FROM peso_corporal WHERE usuario_id = ? ORDER BY data_registro ASC";
    const rows = await executeQuery(sql, [users[0].id]);
    
    // Mapeia para formato que o gráfico entende
    const mapped = rows.map(r => ({ weight: parseFloat(r.peso), date: r.data_registro }));
    res.json(mapped);
});

app.post('/api/peso', requireAuth, async (req, res) => {
    const { user_email, weight, date } = req.body;
    const users = await executeQuery("SELECT id FROM usuarios WHERE email = ?", [user_email]);
    if (!users.length) return res.status(404).json({ error: "User not found" });

    const sql = "INSERT INTO peso_corporal (usuario_id, peso, data_registro) VALUES (?, ?, ?)";
    await executeQuery(sql, [users[0].id, weight, date]);
    res.json({ success: true });
});

// 5. BIBLIOTECA (Sugestões de exercícios)
app.get('/api/biblioteca', async (req, res) => {
    const rows = await executeQuery("SELECT * FROM biblioteca_exercicios");
    res.json(rows);
});

// --- ROTA ROOT ---
// Esta é a rota que resolve o erro "Cannot GET /"
app.get('/', (req, res) => {
    const filePath = path.join(__dirname, 'index.html');
    
    // Verifica se o arquivo existe antes de enviar
    if (fs.existsSync(filePath)) {
        res.sendFile(filePath);
    } else {
        res.status(404).send(`
            <h1>Erro: index.html não encontrado</h1>
            <p>O arquivo <code>index.html</code> deve estar na mesma pasta que o <code>server.js</code>.</p>
            <p>Pasta atual: ${__dirname}</p>
        `);
    }
});

// Inicia Servidor
app.listen(PORT, () => {
    console.log(`\n🚀 Servidor rodando na porta ${PORT}`);
    console.log(`📂 Pasta do projeto: ${__dirname}`);
    console.log(`📡 Acesse: http://localhost:${PORT}\n`);
});