from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from models import (
    Usuario, Perfil, Preferencia, Interesse,
    Curtida, Match, Conversa, Mensagem, Denuncia, Bloqueio
)


class UsuarioRepository:
    def __init__(self, db: Session):
        self.db = db

    def buscar_por_email(self, email: str):
        return self.db.query(Usuario).filter(Usuario.email == email.lower().strip()).first()

    def buscar_por_id(self, id_usuario: int):
        return self.db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()

    def salvar(self, usuario: Usuario):
        self.db.add(usuario)
        self.db.commit()
        self.db.refresh(usuario)
        return usuario


class PerfilRepository:
    def __init__(self, db: Session):
        self.db = db

    def buscar_por_usuario(self, id_usuario: int):
        return self.db.query(Perfil).filter(Perfil.id_usuario == id_usuario).first()

    def listar_todos_exceto(self, ids_excluidos: set[int]):
        return (
            self.db.query(Perfil)
            .join(Usuario, Usuario.id_usuario == Perfil.id_usuario)
            .filter(
                ~Perfil.id_usuario.in_(ids_excluidos),
                Usuario.status == "ATIVO",
                Usuario.is_admin == False,
            )
            .all()
        )

    def listar_interesses(self):
        return self.db.query(Interesse).order_by(Interesse.categoria, Interesse.nome).all()

    def buscar_interesses_por_ids(self, ids: list[int]):
        return self.db.query(Interesse).filter(Interesse.id_interesse.in_(ids)).all()

    def atualizar(self):
        self.db.commit()


class CurtidaRepository:
    def __init__(self, db: Session):
        self.db = db

    def buscar_interacao(self, origem: int, destino: int):
        return (
            self.db.query(Curtida)
            .filter(Curtida.usuario_origem == origem, Curtida.usuario_destino == destino)
            .first()
        )

    def registrar_curtida(self, origem: int, destino: int, tipo: str = "LIKE"):
        existente = self.buscar_interacao(origem, destino)
        if existente:
            existente.tipo = tipo
            self.db.commit()
            return existente
        nova = Curtida(
            usuario_origem=origem,
            usuario_destino=destino,
            tipo=tipo,
            status="AguardandoReciprocidade" if tipo == "LIKE" else "Recusado",
        )
        self.db.add(nova)
        self.db.commit()
        self.db.refresh(nova)
        return nova

    def verificar_curtida_mutua(self, usuario_a: int, usuario_b: int) -> bool:
        reciproca = (
            self.db.query(Curtida)
            .filter(
                Curtida.usuario_origem == usuario_b,
                Curtida.usuario_destino == usuario_a,
                Curtida.tipo == "LIKE",
            )
            .first()
        )
        return reciproca is not None

    def listar_ids_ja_avaliados(self, id_usuario: int) -> set[int]:
        rows = self.db.query(Curtida.usuario_destino).filter(Curtida.usuario_origem == id_usuario).all()
        return {r[0] for r in rows}


class MatchRepository:
    def __init__(self, db: Session):
        self.db = db

    def buscar_match_entre(self, u1: int, u2: int):
        return (
            self.db.query(Match)
            .filter(
                or_(
                    and_(Match.usuario_a == u1, Match.usuario_b == u2),
                    and_(Match.usuario_a == u2, Match.usuario_b == u1),
                )
            )
            .first()
        )

    def buscar_por_id(self, id_match: int):
        return self.db.query(Match).filter(Match.id_match == id_match).first()

    def criar_match_e_conversa(self, u1: int, u2: int):
        existente = self.buscar_match_entre(u1, u2)
        if existente:
            existente.status = "MatchAtivo"
            if existente.conversa:
                existente.conversa.status = "ConversaDisponivel"
            self.db.commit()
            return existente

        novo_match = Match(usuario_a=min(u1, u2), usuario_b=max(u1, u2), status="MatchAtivo")
        self.db.add(novo_match)
        self.db.flush()

        conversa = Conversa(id_match=novo_match.id_match, status="ConversaDisponivel")
        self.db.add(conversa)
        self.db.commit()
        self.db.refresh(novo_match)
        return novo_match

    def listar_matches_ativos_usuario(self, id_usuario: int):
        return (
            self.db.query(Match)
            .filter(
                or_(Match.usuario_a == id_usuario, Match.usuario_b == id_usuario),
                Match.status == "MatchAtivo",
            )
            .order_by(Match.data_hora.desc())
            .all()
        )


class MensagemRepository:
    def __init__(self, db: Session):
        self.db = db

    def salvar_mensagem(self, id_conversa: int, id_remetente: int, conteudo: str):
        msg = Mensagem(id_conversa=id_conversa, id_remetente=id_remetente, conteudo=conteudo)
        self.db.add(msg)
        conversa = self.db.query(Conversa).filter(Conversa.id_conversa == id_conversa).first()
        if conversa and conversa.status == "ConversaDisponivel":
            conversa.status = "ConversaEmAndamento"
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def listar_por_conversa(self, id_conversa: int):
        return (
            self.db.query(Mensagem)
            .filter(Mensagem.id_conversa == id_conversa)
            .order_by(Mensagem.data_hora.asc())
            .all()
        )


class ModeracaoRepository:
    def __init__(self, db: Session):
        self.db = db

    def registrar_bloqueio(self, origem: int, bloqueado: int, motivo: str):
        existente = (
            self.db.query(Bloqueio)
            .filter(Bloqueio.usuario_origem == origem, Bloqueio.usuario_bloqueado == bloqueado)
            .first()
        )
        if existente:
            return existente
        b = Bloqueio(usuario_origem=origem, usuario_bloqueado=bloqueado, motivo=motivo)
        self.db.add(b)
        self.db.commit()
        self.db.refresh(b)
        return b

    def verificar_bloqueio_entre(self, u1: int, u2: int) -> bool:
        b = (
            self.db.query(Bloqueio)
            .filter(
                or_(
                    and_(Bloqueio.usuario_origem == u1, Bloqueio.usuario_bloqueado == u2),
                    and_(Bloqueio.usuario_origem == u2, Bloqueio.usuario_bloqueado == u1),
                )
            )
            .first()
        )
        return b is not None

    def listar_ids_bloqueados_ou_denunciados(self, id_usuario: int) -> set[int]:
        bloq_enviados = self.db.query(Bloqueio.usuario_bloqueado).filter(Bloqueio.usuario_origem == id_usuario).all()
        bloq_recebidos = self.db.query(Bloqueio.usuario_origem).filter(Bloqueio.usuario_bloqueado == id_usuario).all()
        denunciados = self.db.query(Denuncia.denunciado).filter(Denuncia.denunciante == id_usuario).all()
        return {r[0] for r in bloq_enviados} | {r[0] for r in bloq_recebidos} | {r[0] for r in denunciados}

    def registrar_denuncia(self, denunciante: int, denunciado: int, motivo: str, descricao: str):
        d = Denuncia(
            denunciante=denunciante,
            denunciado=denunciado,
            motivo=motivo,
            descricao=descricao,
            status="Pendente",
        )
        self.db.add(d)
        self.db.commit()
        self.db.refresh(d)
        return d

    def listar_denuncias(self):
        return self.db.query(Denuncia).order_by(Denuncia.id_denuncia.desc()).all()

    def buscar_denuncia(self, id_denuncia: int):
        return self.db.query(Denuncia).filter(Denuncia.id_denuncia == id_denuncia).first()
