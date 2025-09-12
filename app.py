# -*- coding: utf-8 -*-
import pandas as pd
from flask import Flask, jsonify, request
from flask_swagger_ui import get_swaggerui_blueprint
import os
import glob
from collections import defaultdict
import re

app = Flask(__name__)

# --- Configuração do Swagger ---
SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': "API Cronograma de Estudos (Nova Estrutura)"}
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# --- Variável para armazenar o cronograma processado ---
cronograma_final = {}

# --- Funções Auxiliares ---

def criar_chave_semana(semana_str):
    """
    Cria uma chave única e limpa para a semana (ex: "Semana 1 (..)" -> "semana_1").
    Retorna None se não encontrar um número.
    """
    numeros = re.findall(r'\d+', semana_str)
    if numeros:
        return f"semana_{numeros[0]}"
    return None

def extrair_periodo(semana_str):
    """Extrai o período da string da semana (ex: "Semana 1 (15/09 a 21/09)..." -> "15/09 a 21/09")"""
    match = re.search(r'\((.*?)\)', semana_str)
    if match:
        return match.group(1)
    return ""

def extrair_area_conhecimento(semana_str):
    """Extrai a área de conhecimento da string da semana (ex: "...Médica" -> "Clínica Médica")"""
    partes = re.split(r'\)\s*', semana_str, 1)
    if len(partes) > 1:
        return partes[1].strip()
    return ""

def extrair_tema_subtema(tema_completo_str):
    """
    Divide a string 'Tema do dia' em Tema Principal e Subtema.
    Ex: "Cardiologia - Hipertensão Arterial Sistêmica" -> ("Cardiologia", "Hipertensão Arterial Sistêmica")
    """
    if ' - ' in tema_completo_str:
        partes = tema_completo_str.split(' - ', 1)
        return partes[0].strip(), partes[1].strip()
    return tema_completo_str.strip(), ""

# --- Funções de Processamento de Dados ---

def processar_arquivos_para_hierarquia(pasta_arquivos):
    """
    Processa arquivos e constrói uma estrutura hierárquica usando dicionários,
    onde cada semana é uma chave única.
    """
    dados_brutos = defaultdict(lambda: {
        "nome_exibicao": "",
        "numero": 0,
        "periodo": "",
        "area_conhecimento": "",
        "dias": defaultdict(lambda: {
            "nome": "",
            "temas": defaultdict(lambda: {
                "nome": "",
                "subtemas": defaultdict(lambda: {
                    "nome": "",
                    "aulas": []
                })
            })
        })
    })

    arquivos = glob.glob(os.path.join(pasta_arquivos, '*.xlsx')) + glob.glob(os.path.join(pasta_arquivos, '*.csv'))
    
    if not arquivos:
        print(f"Nenhum arquivo .xlsx ou .csv encontrado na pasta '{pasta_arquivos}'.")
        return {}

    for arquivo in arquivos:
        try:
            df = pd.read_excel(arquivo) if arquivo.endswith('.xlsx') else pd.read_csv(arquivo)
            df = df.astype(str).fillna('')

            for _, row in df.iterrows():
                semana_str = row.get('Semana', '').strip()
                dia_str = row.get('Dia', '').strip()
                tema_completo_str = row.get('Tema do dia', '').strip()
                aula_str = row.get('Aula', '').strip() # Esta coluna pode não existir na nova planilha, o que está ok.

                chave_semana = criar_chave_semana(semana_str)
                
                # Pula a linha se não conseguir gerar uma chave para a semana ou se o dia/tema estiverem vazios
                if not chave_semana or not dia_str or not tema_completo_str:
                    continue

                tema_principal_str, subtema_str = extrair_tema_subtema(tema_completo_str)
                
                # --- Constrói a hierarquia aninhada ---
                semana_obj = dados_brutos[chave_semana]
                semana_obj["nome_exibicao"] = semana_str
                semana_obj["numero"] = int(re.findall(r'\d+', semana_str)[0])
                semana_obj["periodo"] = extrair_periodo(semana_str)
                semana_obj["area_conhecimento"] = extrair_area_conhecimento(semana_str)

                dia_obj = semana_obj["dias"][dia_str]
                dia_obj["nome"] = dia_str

                tema_obj = dia_obj["temas"][tema_principal_str]
                tema_obj["nome"] = tema_principal_str

                subtema_obj = tema_obj["subtemas"][subtema_str]
                subtema_obj["nome"] = subtema_str
                
                aula_nova = {
                    "nome": aula_str,
                    "link_aula": row.get('Link Aula', '').strip(),
                    "link_gratuito": row.get('Link Gratuito', '').strip()
                }
                if aula_nova not in subtema_obj["aulas"]:
                    subtema_obj["aulas"].append(aula_nova)

        except Exception as e:
            print(f"Erro ao processar o arquivo {arquivo}: {e}")

    return formatar_cronograma_final(dados_brutos)

def formatar_cronograma_final(dados_brutos):
    """
    Converte os dicionários aninhados em listas (para dias, temas, etc.) e
    mantém a estrutura de dicionário para as semanas, ordenando-as por número.
    """
    cronograma_ordenado = {}
    # Ordena as semanas pelo número extraído para garantir a ordem correta
    chaves_ordenadas = sorted(dados_brutos.keys(), key=lambda k: dados_brutos[k]['numero'])

    for chave_semana in chaves_ordenadas:
        semana_val = dados_brutos[chave_semana]
        dias_lista = []
        # Ordena os dias pelo nome (ex: "15/09", "16/09")
        for dia_key in sorted(semana_val["dias"].keys()):
            dia_val = semana_val["dias"][dia_key]
            temas_lista = []
            for tema_key in sorted(dia_val["temas"].keys()):
                tema_val = dia_val["temas"][tema_key]
                subtemas_lista = list(tema_val["subtemas"].values()) # Converte para lista
                tema_val["subtemas"] = subtemas_lista
                temas_lista.append(tema_val)

            dia_val["temas"] = temas_lista
            dias_lista.append(dia_val)

        semana_val["dias"] = dias_lista
        cronograma_ordenado[chave_semana] = semana_val
    
    return {"cronograma": cronograma_ordenado}

# --- Endpoints da API ---

@app.route('/')
def home():
    return """
    <h1>API Cronograma de Estudos (Nova Estrutura)</h1>
    <p>A API agora retorna um dicionário de semanas para acesso direto.</p>
    <p>Endpoints disponíveis:</p>
    <ul>
        <li><a href="/api/cronograma">/api/cronograma</a> - Retorna o cronograma completo na nova estrutura.</li>
        <li><a href="/api/docs">/api/docs</a> - Documentação Swagger.</li>
    </ul>
    """

@app.route('/api/cronograma', methods=['GET'])
def get_cronograma_completo():
    """
    Retorna toda a estrutura do cronograma como um dicionário de semanas.
    ---
    tags:
      - Cronograma
    responses:
      200:
        description: >
          Estrutura completa do cronograma, onde a chave de cada semana
          é um identificador único (ex: 'semana_1').
    """
    return jsonify(cronograma_final)

@app.route('/api/buscar', methods=['GET'])
def buscar():
    """
    Busca flexível por um termo. Retorna uma lista de aulas que correspondem à busca.
    ---
    tags:
      - Busca
    parameters:
      - name: q
        in: query
        type: string
        required: true
        description: Termo a ser buscado (ex: 'Cardiologia', 'Clínica Médica', '15/09').
    responses:
      200:
        description: Uma lista de resultados encontrados.
      400:
        description: Erro se o parâmetro 'q' não for fornecido.
    """
    termo = request.args.get('q', '').lower()
    if not termo:
        return jsonify({"error": "Parâmetro de busca 'q' é obrigatório"}), 400

    resultados = []
    # Itera sobre os valores do dicionário de semanas
    for chave_semana, semana in cronograma_final.get("cronograma", {}).items():
        # Constrói uma string com os dados da semana para busca
        semana_busca = f"{chave_semana} {semana['nome_exibicao']} {semana['area_conhecimento']} {semana['periodo']}".lower()

        if termo in semana_busca:
             # Se o termo for encontrado na semana, adiciona todos os dias daquela semana
             for dia in semana.get("dias", []):
                 resultados.append({
                    "semana": chave_semana,
                    "dia": dia['nome'],
                    "area_conhecimento": semana['area_conhecimento'],
                    "temas": [t for t in dia.get('temas', [])], # Adiciona os temas encontrados
                    "aula_encontrada": []
                 })
             continue
        
        for dia in semana.get("dias", []):
            dia_busca = f"{dia['nome']}".lower()
            if termo in dia_busca:
                resultados.append({
                    "semana": chave_semana,
                    "dia": dia['nome'],
                    "area_conhecimento": semana['area_conhecimento'],
                    "temas": [t for t in dia.get('temas', [])],
                    "aula_encontrada": []
                })
                continue
            for tema in dia.get("temas", []):
                for subtema in tema.get("subtemas", []):
                    for aula in subtema.get("aulas", []):
                        # Constrói uma string de busca com todo o caminho
                        caminho_completo = f"{semana_busca} {dia['nome']} {tema['nome']} {subtema['nome']} {aula['nome']}".lower()
                        if termo in caminho_completo:
                            resultados.append({
                                "semana": chave_semana,
                                "dia": dia['nome'],
                                "tema": tema['nome'],
                                "subtema": subtema['nome'],
                                "aula_encontrada": aula
                            })
                            
    return jsonify({"resultados": resultados})

@app.route('/static/swagger.json')
def swagger_spec():
    """Serve a especificação OpenAPI para a UI do Swagger."""
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "API Cronograma de Estudos (Dicionário)",
            "description": "API para acesso ao cronograma de estudos com estrutura de dicionário.",
            "version": "3.0.0"
        },
        "paths": {
            "/api/cronograma": { "get": get_cronograma_completo.__doc__ },
            "/api/buscar": { "get": buscar.__doc__ }
        }
    }
    return jsonify(spec)

# --- Inicialização ---
if __name__ == '__main__':
    pasta_dados = 'dados_cronograma'
    
    if not os.path.exists(pasta_dados):
        os.makedirs(pasta_dados)
        print(f"Pasta '{pasta_dados}' criada.")
        print("Por favor, adicione seus arquivos .xlsx ou .csv nesta pasta e reinicie o servidor.")
    
    print("Processando arquivos do cronograma...")
    cronograma_final = processar_arquivos_para_hierarquia(pasta_dados)
    
    if cronograma_final.get("cronograma"):
        num_semanas = len(cronograma_final.get("cronograma", {}))
        print(f"Processamento concluído. {num_semanas} semanas carregadas.")
        print("API pronta para receber requisições.")
    else:
        print("Nenhum dado de cronograma foi carregado. A API retornará resultados vazios.")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)