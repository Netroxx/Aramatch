from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, Date, ForeignKey, Table, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "sqlite:///./aramatch.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Tabela associativa N:N entre PERFIL e INTERESSE
perfil_interesse = Table(
    "PERFIL_INTERESSE",
    Base.metadata,
    Column("id_perfil", Integer, ForeignKey("PERFIL.id_perfil", ondelete="CASCADE"), primary_key=True),
    Column("id_interesse", Integer, ForeignKey("INTERESSE.id_interesse", ondelete="CASCADE"), primary_key=True),
)


class Usuario(Base):
    __tablename__ = "USUARIO"

    id_usuario = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    senha_hash = Column(String(256), nullable=False)
    data_nascimento = Column(Date, nullable=True)
    universidade = Column(String(120), nullable=False)
    curso = Column(String(120), nullable=False)
    status = Column(String(30), default="ATIVO")  # ATIVO, SUSPENSO, BANIDO
    is_admin = Column(Boolean, default=False)

    perfil = relationship("Perfil", back_populates="usuario", uselist=False, cascade="all, delete-orphan")


class Perfil(Base):
    __tablename__ = "PERFIL"

    id_perfil = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), unique=True, nullable=False)
    foto = Column(String(500), default="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400")
    bio = Column(String(500), default="")
    idade = Column(Integer, default=20)
    curso = Column(String(120), nullable=False)
    periodo = Column(String(30), default="1º Período")
    universidade = Column(String(120), nullable=False)
    tipo_conexao = Column(String(30), default="AMBOS")  # AMIZADE, RELACIONAMENTO, AMBOS

    usuario = relationship("Usuario", back_populates="perfil")
    preferencia = relationship("Preferencia", back_populates="perfil", uselist=False, cascade="all, delete-orphan")
    interesses = relationship("Interesse", secondary=perfil_interesse, back_populates="perfis")


class Preferencia(Base):
    __tablename__ = "PREFERENCIA"

    id_preferencia = Column(Integer, primary_key=True, index=True)
    id_perfil = Column(Integer, ForeignKey("PERFIL.id_perfil", ondelete="CASCADE"), unique=True, nullable=False)
    tipo_conexao = Column(String(30), default="AMBOS")  # AMIZADE, RELACIONAMENTO, AMBOS
    idade_min = Column(Integer, default=18)
    idade_max = Column(Integer, default=35)
    curso_preferido = Column(String(120), default="TODOS")
    raio_km = Column(Integer, default=50)

    perfil = relationship("Perfil", back_populates="preferencia")


class Interesse(Base):
    __tablename__ = "INTERESSE"

    id_interesse = Column(Integer, primary_key=True, index=True)
    nome = Column(String(80), unique=True, nullable=False)
    categoria = Column(String(80), nullable=False)  # Academico, Social, Pessoal

    perfis = relationship("Perfil", secondary=perfil_interesse, back_populates="interesses")


class Curtida(Base):
    __tablename__ = "CURTIDA"

    id_curtida = Column(Integer, primary_key=True, index=True)
    usuario_origem = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    usuario_destino = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(20), default="LIKE")  # LIKE, DISLIKE
    status = Column(String(30), default="CurtidaRegistrada")
    data_hora = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("usuario_origem", "usuario_destino", name="uq_curtida_par"),)


class Match(Base):
    __tablename__ = "MATCH"

    id_match = Column(Integer, primary_key=True, index=True)
    usuario_a = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    usuario_b = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    status = Column(String(30), default="MatchAtivo")  # MatchAtivo, MatchDesfeito, MatchBloqueado
    data_hora = Column(DateTime, default=datetime.utcnow)

    conversa = relationship("Conversa", back_populates="match", uselist=False, cascade="all, delete-orphan")


class Conversa(Base):
    __tablename__ = "CONVERSA"

    id_conversa = Column(Integer, primary_key=True, index=True)
    id_match = Column(Integer, ForeignKey("MATCH.id_match", ondelete="CASCADE"), unique=True, nullable=False)
    status = Column(String(30), default="ConversaDisponivel")  # ConversaDisponivel, ConversaEmAndamento, Encerrada
    data_criacao = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match", back_populates="conversa")
    mensagens = relationship("Mensagem", back_populates="conversa", cascade="all, delete-orphan")


class Mensagem(Base):
    __tablename__ = "MENSAGEM"

    id_mensagem = Column(Integer, primary_key=True, index=True)
    id_conversa = Column(Integer, ForeignKey("CONVERSA.id_conversa", ondelete="CASCADE"), nullable=False)
    id_remetente = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    conteudo = Column(String(1000), nullable=False)
    data_hora = Column(DateTime, default=datetime.utcnow)
    lida = Column(Boolean, default=False)

    conversa = relationship("Conversa", back_populates="mensagens")


class Denuncia(Base):
    __tablename__ = "DENUNCIA"

    id_denuncia = Column(Integer, primary_key=True, index=True)
    denunciante = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    denunciado = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    motivo = Column(String(120), nullable=False)
    descricao = Column(String(500), nullable=False)
    data_denuncia = Column(Date, default=date.today)
    # Ciclo de vida do Diagrama de Estados: Pendente, EmAnalise, Procedente, Improcedente,
    # SolicitandoMaisInformacoes, MedidaAplicada, Concluida, Arquivada, Cancelada
    status = Column(String(40), default="Pendente")


class Bloqueio(Base):
    __tablename__ = "BLOQUEIO"

    id_bloqueio = Column(Integer, primary_key=True, index=True)
    usuario_origem = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    usuario_bloqueado = Column(Integer, ForeignKey("USUARIO.id_usuario", ondelete="CASCADE"), nullable=False)
    motivo = Column(String(200), default="Bloqueio pelo utilizador")
    data_hora = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("usuario_origem", "usuario_bloqueado", name="uq_bloqueio_par"),)


def init_db():
    Base.metadata.create_all(bind=engine)
