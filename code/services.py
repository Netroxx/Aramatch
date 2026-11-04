import hashlib
import hmac
import os
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models import Usuario, Perfil, Preferencia
from repositories import (
    UsuarioRepository, PerfilRepository, CurtidaRepository,
    MatchRepository, MensagemRepository, ModeracaoRepository
)

SECRET_SALT = os.getenv("ARAMATCH_SALT", "aramatch-puc-salt-2026")


def gerar_hash_senha(senha: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), SECRET_SALT.encode("utf-8"), 100_000)
    return dk.hex()


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return hmac.compare_digest(gerar_hash_senha(senha), senha_hash)


class UsuarioService:
    def __init__(self, db: Session):
        self.db = db
        self.usuario_repo = UsuarioRepository(db)
        self.perfil_repo = PerfilRepository(db)

    # Contrato UC-01: cadastrarUsuario(nome, email, senha, universidade, curso)
    def cadastrar_usuario(
        self, nome: str, email: str, senha: str, universidade: str, curso: str,
        idade: int = 20, periodo: str = "1º Período", tipo_conexao: str = "AMBOS"
    ):
        if not all([nome.strip(), email.strip(), senha.strip(), universidade.strip(), curso.strip()]):
            raise HTTPException(status_code=400, detail="Todos os campos obrigatórios devem ser preenchidos.")

        if self.usuario_repo.buscar_por_email(email):
            raise HTTPException(status_code=409, detail="O endereço de e-mail informado já está em uso.")

        novo_usuario = Usuario(
            nome=nome.strip(),
            email=email.lower().strip(),
            senha_hash=gerar_hash_senha(senha),
            universidade=universidade.strip(),
            curso=curso.strip(),
            status="ATIVO",
        )
        self.db.add(novo_usuario)
        self.db.flush()

        perfil_inicial = Perfil(
            id_usuario=novo_usuario.id_usuario,
            curso=curso.strip(),
            universidade=universidade.strip(),
            idade=idade,
            periodo=periodo,
            tipo_conexao=tipo_conexao,
            bio=f"Estudante de {curso.strip()} na {universidade.strip()}.",
        )
        self.db.add(perfil_inicial)
        self.db.flush()

        pref_inicial = Preferencia(
            id_perfil=perfil_inicial.id_perfil,
            tipo_conexao=tipo_conexao,
            idade_min=18,
            idade_max=35,
            curso_preferido="TODOS",
        )
        self.db.add(pref_inicial)
        self.db.commit()
        self.db.refresh(novo_usuario)
        return novo_usuario

    def autenticar(self, email: str, senha: str):
        usuario = self.usuario_repo.buscar_por_email(email)
        if not usuario or not verificar_senha(senha, usuario.senha_hash):
            raise HTTPException(status_code=401, detail="E-mail ou palavra-passe inválidos.")
        if usuario.status != "ATIVO":
            raise HTTPException(status_code=403, detail=f"Conta indisponível ({usuario.status}).")
        return usuario


class RecomendacaoService:
    def __init__(self, db: Session):
        self.perfil_repo = PerfilRepository(db)
        self.curtida_repo = CurtidaRepository(db)
        self.moderacao_repo = ModeracaoRepository(db)

    # UC-05 / RN-01, RN-03, RN-04, RN-06, RN-08
    def listar_sugestoes(self, id_usuario: int):
        meu_perfil = self.perfil_repo.buscar_por_usuario(id_usuario)
        if not meu_perfil:
            return []

        pref = meu_perfil.preferencia
        meus_interesses = {i.id_interesse for i in meu_perfil.interesses}

        excluidos = {id_usuario}
        excluidos |= self.curtida_repo.listar_ids_ja_avaliados(id_usuario)
        excluidos |= self.moderacao_repo.listar_ids_bloqueados_ou_denunciados(id_usuario)

        candidatos = self.perfil_repo.listar_todos_exceto(excluidos)
        sugestoes = []

        for p in candidatos:
            # Filtro de faixa etária e tipo de conexão da preferência
            if pref:
                if not (pref.idade_min <= p.idade <= pref.idade_max):
                    continue
                if pref.tipo_conexao != "AMBOS" and p.tipo_conexao not in ("AMBOS", pref.tipo_conexao):
                    continue
                if pref.curso_preferido and pref.curso_preferido != "TODOS":
                    if pref.curso_preferido.lower() not in p.curso.lower():
                        continue

            # Cálculo de compatibilidade (RN-06: interesses, universidade, curso, tipo de conexão)
            interesses_candidato = {i.id_interesse for i in p.interesses}
            em_comum = meus_interesses & interesses_candidato
            pontos = len(em_comum) * 25
            if p.universidade.lower() == meu_perfil.universidade.lower():
                pontos += 20
            if p.curso.lower() == meu_perfil.curso.lower():
                pontos += 15
            if p.tipo_conexao == meu_perfil.tipo_conexao or p.tipo_conexao == "AMBOS":
                pontos += 15
            score = min(99, max(40, pontos))

            sugestoes.append({
                "id_usuario": p.id_usuario,
                "id_perfil": p.id_perfil,
                "nome": p.usuario.nome,
                "idade": p.idade,
                "universidade": p.universidade,
                "curso": p.curso,
                "periodo": p.periodo,
                "bio": p.bio,
                "foto": p.foto,
                "tipo_conexao": p.tipo_conexao,
                "interesses": [{"id": i.id_interesse, "nome": i.nome, "categoria": i.categoria} for i in p.interesses],
                "interesses_em_comum": len(em_comum),
                "compatibilidade": score,
            })

        sugestoes.sort(key=lambda x: x["compatibilidade"], reverse=True)
        return sugestoes


class MatchService:
    def __init__(self, db: Session):
        self.curtida_repo = CurtidaRepository(db)
        self.match_repo = MatchRepository(db)
        self.moderacao_repo = ModeracaoRepository(db)
        self.usuario_repo = UsuarioRepository(db)

    # Contrato UC-06 e UC-07: curtirPerfil(idUsuario, idPerfilCurtido)
    def processar_curtida(self, id_usuario: int, id_usuario_alvo: int, tipo: str = "LIKE"):
        if id_usuario == id_usuario_alvo:
            raise HTTPException(status_code=400, detail="Não é possível curtir o próprio perfil.")

        alvo = self.usuario_repo.buscar_por_id(id_usuario_alvo)
        if not alvo or alvo.status != "ATIVO":
            raise HTTPException(status_code=404, detail="Perfil pretendido não está disponível.")

        if self.moderacao_repo.verificar_bloqueio_entre(id_usuario, id_usuario_alvo):
            raise HTTPException(status_code=403, detail="Interação indisponível devido a bloqueio.")

        curtida = self.curtida_repo.registrar_curtida(id_usuario, id_usuario_alvo, tipo)

        if tipo == "DISLIKE":
            return {"status": "PerfilRecusado", "match_criado": False, "id_match": None}

        if self.curtida_repo.verificar_curtida_mutua(id_usuario, id_usuario_alvo):
            curtida.status = "MatchAtivo"
            novo_match = self.match_repo.criar_match_e_conversa(id_usuario, id_usuario_alvo)
            return {
                "status": "MatchAtivo",
                "match_criado": True,
                "id_match": novo_match.id_match,
                "parceiro_nome": alvo.nome,
            }

        return {"status": "AguardandoReciprocidade", "match_criado": False, "id_match": None}

    # UC-12 / RN-07: Desfazer match
    def desfazer_match(self, id_usuario: int, id_match: int):
        match = self.match_repo.buscar_por_id(id_match)
        if not match or id_usuario not in (match.usuario_a, match.usuario_b):
            raise HTTPException(status_code=404, detail="Match não encontrado.")
        match.status = "MatchDesfeito"
        if match.conversa:
            match.conversa.status = "Encerrada"
        self.match_repo.db.commit()
        return {"status": "MatchDesfeito"}


class MensagemService:
    def __init__(self, db: Session):
        self.match_repo = MatchRepository(db)
        self.msg_repo = MensagemRepository(db)
        self.moderacao_repo = ModeracaoRepository(db)

    # Contrato UC-08: enviarMensagem(idRemetente, idDestinatario, conteudoMensagem)
    def enviar_mensagem(self, id_remetente: int, id_match: int, conteudo: str):
        if not conteudo or not conteudo.strip():
            raise HTTPException(status_code=400, detail="O conteúdo da mensagem não pode estar vazio.")

        match = self.match_repo.buscar_por_id(id_match)
        if not match or id_remetente not in (match.usuario_a, match.usuario_b):
            raise HTTPException(status_code=404, detail="Match inexistente para este utilizador.")

        if match.status != "MatchAtivo":
            raise HTTPException(
                status_code=403,
                detail=f"Envio não permitido: o match não está ativo ({match.status}).",
            )

        id_destinatario = match.usuario_b if match.usuario_a == id_remetente else match.usuario_a
        if self.moderacao_repo.verificar_bloqueio_entre(id_remetente, id_destinatario):
            raise HTTPException(status_code=403, detail="Envio impedido por bloqueio entre os utilizadores.")

        msg = self.msg_repo.salvar_mensagem(match.conversa.id_conversa, id_remetente, conteudo.strip())
        return msg


class ModeracaoService:
    def __init__(self, db: Session):
        self.mod_repo = ModeracaoRepository(db)
        self.match_repo = MatchRepository(db)
        self.usuario_repo = UsuarioRepository(db)

    # UC-11 / RN-04: Bloquear utilizador e atualizar estado do Match para MatchBloqueado
    def bloquear_usuario(self, id_origem: int, id_bloqueado: int, motivo: str):
        bloqueio = self.mod_repo.registrar_bloqueio(id_origem, id_bloqueado, motivo)
        match = self.match_repo.buscar_match_entre(id_origem, id_bloqueado)
        if match:
            match.status = "MatchBloqueado"
            if match.conversa:
                match.conversa.status = "Encerrada"
            self.match_repo.db.commit()
        return bloqueio

    # UC-09: Denunciar utilizador
    def denunciar_usuario(self, id_denunciante: int, id_denunciado: int, motivo: str, descricao: str):
        return self.mod_repo.registrar_denuncia(id_denunciante, id_denunciado, motivo, descricao)

    # UC-10: Gerir denúncias conforme o Diagrama de Estados da Denúncia
    def atualizar_status_denuncia(self, id_denuncia: int, novo_status: str, suspender_denunciado: bool = False):
        estados_validos = {
            "Pendente", "EmAnalise", "Procedente", "Improcedente",
            "SolicitandoMaisInformacoes", "MedidaAplicada", "Concluida", "Arquivada", "Cancelada"
        }
        if novo_status not in estados_validos:
            raise HTTPException(status_code=400, detail="Estado de denúncia inválido.")

        denuncia = self.mod_repo.buscar_denuncia(id_denuncia)
        if not denuncia:
            raise HTTPException(status_code=404, detail="Denúncia não encontrada.")

        denuncia.status = novo_status
        if suspender_denunciado or novo_status == "MedidaAplicada":
            u = self.usuario_repo.buscar_por_id(denuncia.denunciado)
            if u:
                u.status = "SUSPENSO"
        self.mod_repo.db.commit()
        self.mod_repo.db.refresh(denuncia)
        return denuncia
