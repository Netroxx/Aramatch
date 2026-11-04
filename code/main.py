from datetime import datetime, timedelta
from typing import Optional
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from models import init_db, SessionLocal, Usuario, Interesse, Curtida
from repositories import PerfilRepository, MatchRepository, MensagemRepository, ModeracaoRepository, UsuarioRepository
from services import (
    UsuarioService, RecomendacaoService, MatchService,
    MensagemService, ModeracaoService, gerar_hash_senha
)

JWT_SECRET = "aramatch-jwt-secret-key-2026"
JWT_ALG = "HS256"

app = FastAPI(title="AraMatch API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def criar_token(usuario: Usuario) -> str:
    payload = {
        "sub": str(usuario.id_usuario),
        "email": usuario.email,
        "is_admin": usuario.is_admin,
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def get_usuario_atual(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> Usuario:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token de autenticação em falta.")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        id_usuario = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")

    usuario = UsuarioRepository(db).buscar_por_id(id_usuario)
    if not usuario or usuario.status != "ATIVO":
        raise HTTPException(status_code=401, detail="Utilizador inválido ou inativo.")
    return usuario


# Schemas Pydantic
class CadastroSchema(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    universidade: str
    curso: str
    idade: int = 21
    periodo: str = "4º Período"
    tipo_conexao: str = "AMBOS"


class LoginSchema(BaseModel):
    email: EmailStr
    senha: str


class AtualizarPerfilSchema(BaseModel):
    bio: str
    foto: str
    idade: int
    curso: str
    periodo: str
    universidade: str
    tipo_conexao: str
    interesses_ids: list[int] = []


class AtualizarPreferenciaSchema(BaseModel):
    tipo_conexao: str
    idade_min: int
    idade_max: int
    curso_preferido: str


class CurtidaSchema(BaseModel):
    id_usuario_destino: int
    tipo: str = "LIKE"


class MensagemSchema(BaseModel):
    conteudo: str


class BloqueioSchema(BaseModel):
    id_usuario_bloqueado: int
    motivo: str = "Comportamento indesejado"


class DenunciaSchema(BaseModel):
    id_denunciado: int
    motivo: str
    descricao: str


class AtualizarDenunciaSchema(BaseModel):
    status: str
    suspender_denunciado: bool = False


# Seed inicial para testes imediatos
def seed_database(db: Session):
    if db.query(Interesse).count() == 0:
        interesses_iniciais = [
            Interesse(nome="Engenharia de Software", categoria="Académico"),
            Interesse(nome="Inteligência Artificial", categoria="Académico"),
            Interesse(nome="Maratonas de Programação", categoria="Académico"),
            Interesse(nome="Futebol no Estádio", categoria="Social"),
            Interesse(nome="Festivais e Concertos", categoria="Social"),
            Interesse(nome="Vinhos e Gastronomia", categoria="Social"),
            Interesse(nome="Musculação / Fitness", categoria="Pessoal"),
            Interesse(nome="Gaming / eSports", categoria="Pessoal"),
            Interesse(nome="Viagens e Fotografia", categoria="Pessoal"),
        ]
        db.add_all(interesses_iniciais)
        db.commit()

    if db.query(Usuario).count() == 0:
        u_service = UsuarioService(db)
        todos_interesses = db.query(Interesse).all()

        # Conta de Administrador (Ator Administrador)
        admin = Usuario(
            nome="Administrador AraMatch",
            email="admin@aramatch.edu.br",
            senha_hash=gerar_hash_senha("admin123"),
            universidade="PUC Minas",
            curso="Administração do Sistema",
            status="ATIVO",
            is_admin=True,
        )
        db.add(admin)
        db.commit()

        perfis_demo = [
            {
                "nome": "Mariana Costa",
                "email": "mariana@pucminas.br",
                "universidade": "PUC Minas",
                "curso": "Engenharia de Software",
                "idade": 21,
                "periodo": "6º Período",
                "tipo_conexao": "AMBOS",
                "foto": "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=500",
                "bio": "Apaixonada por arquitetura de software, café pós-aula, jogos competitivos e um bom vinho ao fim de semana.",
                "interesses_idx": [0, 3, 5, 7],
            },
            {
                "nome": "Beatriz Almeida",
                "email": "beatriz@ufmg.br",
                "universidade": "UFMG",
                "curso": "Ciência da Computação",
                "idade": 22,
                "periodo": "7º Período",
                "tipo_conexao": "RELACIONAMENTO",
                "foto": "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=500",
                "bio": "Investigadora em IA, fã de festivais de música eletrónica, viagens fotográficas e treino todos os dias.",
                "interesses_idx": [1, 4, 6, 8],
            },
            {
                "nome": "Lucas Ferreira",
                "email": "lucas@pucminas.br",
                "universidade": "PUC Minas",
                "curso": "Sistemas de Informação",
                "idade": 23,
                "periodo": "8º Período",
                "tipo_conexao": "AMIZADE",
                "foto": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=500",
                "bio": "Procurando parceiros para projetos full-stack, partidas de CS2 à noite e ir ver futebol na quarta-feira.",
                "interesses_idx": [0, 2, 3, 7],
            },
            {
                "nome": "Camila Ribeiro",
                "email": "camila@pucminas.br",
                "universidade": "PUC Minas",
                "curso": "Arquitetura e Urbanismo",
                "idade": 20,
                "periodo": "4º Período",
                "tipo_conexao": "AMBOS",
                "foto": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500",
                "bio": "Adoro fotografia urbana, viagens de praia, descobrir restaurantes novos e concertos ao vivo.",
                "interesses_idx": [4, 5, 8],
            },
        ]

        criados = []
        for d in perfis_demo:
            u = u_service.cadastrar_usuario(
                nome=d["nome"],
                email=d["email"],
                senha="123456",
                universidade=d["universidade"],
                curso=d["curso"],
                idade=d["idade"],
                periodo=d["periodo"],
                tipo_conexao=d["tipo_conexao"],
            )
            u.perfil.foto = d["foto"]
            u.perfil.bio = d["bio"]
            u.perfil.interesses = [todos_interesses[i] for i in d["interesses_idx"]]
            db.commit()
            criados.append(u)

        # Mariana e Beatriz já deixam curtida para o próximo utilizador que se registar (ID 6)
        # ou entre contas demo para demonstrar o fluxo de Match imediato
        db.add(Curtida(usuario_origem=criados[0].id_usuario, usuario_destino=criados[2].id_usuario, tipo="LIKE"))
        db.commit()


@app.on_event("startup")
def startup_event():
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


# Endpoints de Autenticação e Cadastro (UC-01, UC-02)
@app.post("/api/auth/register")
def cadastrar(dados: CadastroSchema, db: Session = Depends(get_db)):
    service = UsuarioService(db)
    usuario = service.cadastrar_usuario(
        nome=dados.nome,
        email=dados.email,
        senha=dados.senha,
        universidade=dados.universidade,
        curso=dados.curso,
        idade=dados.idade,
        periodo=dados.periodo,
        tipo_conexao=dados.tipo_conexao,
    )
    # Para facilitar o teste do utilizador recém-cadastrado, Mariana e Camila curtem-no automaticamente
    for demo_email in ("mariana@pucminas.br", "camila@pucminas.br"):
        demo = UsuarioRepository(db).buscar_por_email(demo_email)
        if demo and demo.id_usuario != usuario.id_usuario:
            db.add(Curtida(usuario_origem=demo.id_usuario, usuario_destino=usuario.id_usuario, tipo="LIKE"))
    db.commit()

    return {
        "token": criar_token(usuario),
        "usuario": {
            "id_usuario": usuario.id_usuario,
            "nome": usuario.nome,
            "email": usuario.email,
            "is_admin": usuario.is_admin,
        },
    }


@app.post("/api/auth/login")
def login(dados: LoginSchema, db: Session = Depends(get_db)):
    service = UsuarioService(db)
    usuario = service.autenticar(dados.email, dados.senha)
    return {
        "token": criar_token(usuario),
        "usuario": {
            "id_usuario": usuario.id_usuario,
            "nome": usuario.nome,
            "email": usuario.email,
            "is_admin": usuario.is_admin,
        },
    }


# Endpoints de Perfil, Interesses e Preferências (UC-03, UC-04)
@app.get("/api/interesses")
def listar_interesses(db: Session = Depends(get_db)):
    itens = PerfilRepository(db).listar_interesses()
    return [{"id_interesse": i.id_interesse, "nome": i.nome, "categoria": i.categoria} for i in itens]


@app.get("/api/perfil/me")
def obter_meu_perfil(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    p = PerfilRepository(db).buscar_por_usuario(usuario.id_usuario)
    if not p:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    pref = p.preferencia
    return {
        "id_usuario": usuario.id_usuario,
        "nome": usuario.nome,
        "email": usuario.email,
        "is_admin": usuario.is_admin,
        "foto": p.foto,
        "bio": p.bio,
        "idade": p.idade,
        "curso": p.curso,
        "periodo": p.periodo,
        "universidade": p.universidade,
        "tipo_conexao": p.tipo_conexao,
        "interesses": [{"id_interesse": i.id_interesse, "nome": i.nome, "categoria": i.categoria} for i in p.interesses],
        "preferencia": {
            "tipo_conexao": pref.tipo_conexao if pref else "AMBOS",
            "idade_min": pref.idade_min if pref else 18,
            "idade_max": pref.idade_max if pref else 35,
            "curso_preferido": pref.curso_preferido if pref else "TODOS",
        },
    }


@app.put("/api/perfil/me")
def atualizar_perfil(
    dados: AtualizarPerfilSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    repo = PerfilRepository(db)
    p = repo.buscar_por_usuario(usuario.id_usuario)
    p.bio = dados.bio
    p.foto = dados.foto
    p.idade = dados.idade
    p.curso = dados.curso
    p.periodo = dados.periodo
    p.universidade = dados.universidade
    p.tipo_conexao = dados.tipo_conexao
    usuario.curso = dados.curso
    usuario.universidade = dados.universidade
    p.interesses = repo.buscar_interesses_por_ids(dados.interesses_ids)
    repo.atualizar()
    return {"mensagem": "Perfil atualizado com sucesso."}


@app.put("/api/preferencias/me")
def atualizar_preferencias(
    dados: AtualizarPreferenciaSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    repo = PerfilRepository(db)
    p = repo.buscar_por_usuario(usuario.id_usuario)
    pref = p.preferencia
    pref.tipo_conexao = dados.tipo_conexao
    pref.idade_min = dados.idade_min
    pref.idade_max = dados.idade_max
    pref.curso_preferido = dados.curso_preferido
    repo.atualizar()
    return {"mensagem": "Preferências atualizadas com sucesso."}


# Endpoints de Recomendação, Curtida e Match (UC-05, UC-06, UC-07, UC-12)
@app.get("/api/sugestoes")
def obter_sugestoes(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    return RecomendacaoService(db).listar_sugestoes(usuario.id_usuario)


@app.post("/api/curtidas")
def curtir_perfil(
    dados: CurtidaSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    return MatchService(db).processar_curtida(usuario.id_usuario, dados.id_usuario_destino, dados.tipo)


@app.get("/api/matches")
def listar_matches(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    matches = MatchRepository(db).listar_matches_ativos_usuario(usuario.id_usuario)
    u_repo = UsuarioRepository(db)
    p_repo = PerfilRepository(db)
    resultado = []
    for m in matches:
        id_parceiro = m.usuario_b if m.usuario_a == usuario.id_usuario else m.usuario_a
        parceiro = u_repo.buscar_por_id(id_parceiro)
        perfil_p = p_repo.buscar_por_usuario(id_parceiro)
        resultado.append({
            "id_match": m.id_match,
            "status": m.status,
            "status_conversa": m.conversa.status if m.conversa else "ConversaDisponivel",
            "data_hora": m.data_hora.isoformat(),
            "parceiro": {
                "id_usuario": parceiro.id_usuario,
                "nome": parceiro.nome,
                "curso": perfil_p.curso if perfil_p else parceiro.curso,
                "universidade": perfil_p.universidade if perfil_p else parceiro.universidade,
                "foto": perfil_p.foto if perfil_p else "",
            },
        })
    return resultado


@app.delete("/api/matches/{id_match}")
def desfazer_match(id_match: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    return MatchService(db).desfazer_match(usuario.id_usuario, id_match)


# Endpoints de Mensagens (UC-08)
@app.get("/api/matches/{id_match}/mensagens")
def listar_mensagens(id_match: int, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    match = MatchRepository(db).buscar_por_id(id_match)
    if not match or usuario.id_usuario not in (match.usuario_a, match.usuario_b):
        raise HTTPException(status_code=404, detail="Match não encontrado.")
    msgs = MensagemRepository(db).listar_por_conversa(match.conversa.id_conversa)
    return [
        {
            "id_mensagem": msg.id_mensagem,
            "id_remetente": msg.id_remetente,
            "conteudo": msg.conteudo,
            "data_hora": msg.data_hora.strftime("%H:%M"),
        }
        for msg in msgs
    ]


@app.post("/api/matches/{id_match}/mensagens")
def enviar_mensagem(
    id_match: int,
    dados: MensagemSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    msg = MensagemService(db).enviar_mensagem(usuario.id_usuario, id_match, dados.conteudo)
    return {
        "id_mensagem": msg.id_mensagem,
        "id_remetente": msg.id_remetente,
        "conteudo": msg.conteudo,
        "data_hora": msg.data_hora.strftime("%H:%M"),
    }


# Endpoints de Moderação: Bloqueio e Denúncia (UC-09, UC-10, UC-11)
@app.post("/api/bloqueios")
def bloquear(dados: BloqueioSchema, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    ModeracaoService(db).bloquear_usuario(usuario.id_usuario, dados.id_usuario_bloqueado, dados.motivo)
    return {"mensagem": "Utilizador bloqueado com sucesso."}


@app.post("/api/denuncias")
def denunciar(dados: DenunciaSchema, usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    d = ModeracaoService(db).denunciar_usuario(
        usuario.id_usuario, dados.id_denunciado, dados.motivo, dados.descricao
    )
    return {"mensagem": "Denúncia registada para análise administrativa.", "id_denuncia": d.id_denuncia}


@app.get("/api/admin/denuncias")
def listar_denuncias_admin(usuario: Usuario = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao Administrador.")
    denuncias = ModeracaoRepository(db).listar_denuncias()
    u_repo = UsuarioRepository(db)
    return [
        {
            "id_denuncia": d.id_denuncia,
            "denunciante_nome": u_repo.buscar_por_id(d.denunciante).nome if u_repo.buscar_por_id(d.denunciante) else str(d.denunciante),
            "denunciado_id": d.denunciado,
            "denunciado_nome": u_repo.buscar_por_id(d.denunciado).nome if u_repo.buscar_por_id(d.denunciado) else str(d.denunciado),
            "motivo": d.motivo,
            "descricao": d.descricao,
            "data_denuncia": d.data_denuncia.isoformat(),
            "status": d.status,
        }
        for d in denuncias
    ]


@app.patch("/api/admin/denuncias/{id_denuncia}")
def atualizar_denuncia_admin(
    id_denuncia: int,
    dados: AtualizarDenunciaSchema,
    usuario: Usuario = Depends(get_usuario_atual),
    db: Session = Depends(get_db),
):
    if not usuario.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito ao Administrador.")
    d = ModeracaoService(db).atualizar_status_denuncia(
        id_denuncia, dados.status, dados.suspender_denunciado
    )
    return {"id_denuncia": d.id_denuncia, "status": d.status}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_spa():
    return FileResponse("static/index.html")
