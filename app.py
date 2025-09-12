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

def processar_arquivos_para_hierarquia():
    """
    Processa arquivos na raiz do projeto e constrói uma estrutura hierárquica agrupada por
    'area_conhecimento'.
    """
    # Usamos defaultdict para criar listas vazias automaticamente para cada nova área
    dados_brutos = defaultdict(list)

    # Busca arquivos .xlsx e .csv diretamente na raiz do projeto
    arquivos = glob.glob('*.xlsx') + glob.glob('*.csv')
    
    if not arquivos:
        print("Nenhum arquivo .xlsx ou .csv encontrado na raiz do projeto.")
        return {}
    else:
        print(f"Arquivos encontrados: {arquivos}")

    for arquivo in arquivos:
        try:
            df = pd.read_excel(arquivo) if arquivo.endswith('.xlsx') else pd.read_csv(arquivo)
            
            if df.empty:
                print(f"Atenção: O arquivo '{os.path.basename(arquivo)}' está vazio ou não pôde ser lido corretamente.")
                continue

            # Normaliza os nomes das colunas
            df.columns = [col.strip().lower() for col in df.columns]
            print(f"Colunas normalizadas no arquivo '{os.path.basename(arquivo)}': {df.columns.tolist()}")

            df = df.astype(str).fillna('')
            print(f"Arquivo '{os.path.basename(arquivo)}' lido com sucesso. Primeiras 5 linhas:")
            print(df.head().to_string())

            for _, row in df.iterrows():
                semana_str = row.get('semana', '').strip()
                dia_str = row.get('dia', '').strip()
                tema_completo_str = row.get('tema do dia', '').strip()
                aula_str = row.get('aula', '').strip() # Esta coluna pode não existir na nova planilha, o que está ok.

                chave_semana = criar_chave_semana(semana_str)
                area_conhecimento_str = extrair_area_conhecimento(semana_str)

                # Pula a linha se não conseguir a area, a chave da semana ou se o dia/tema estiverem vazios
                if not area_conhecimento_str or not chave_semana or not dia_str or not tema_completo_str:
                    continue

                tema_principal_str, subtema_str = extrair_tema_subtema(tema_completo_str)
                
                # --- Constrói a hierarquia de TEMAS e SUBTEMAS ---
                # A lógica abaixo cria a estrutura aninhada, mas de forma separada
                # para cada linha da planilha.
                
                temas_lista = []
                subtemas_lista = []
                aulas_lista = []
                
                aula_nova = {
                    "nome": aula_str,
                    "link_aula": row.get('link aula', '').strip(),
                    "link_gratuito": row.get('link gratuito', '').strip()
                }
                aulas_lista.append(aula_nova)

                subtema_obj = {
                    "nome": subtema_str,
                    "aulas": aulas_lista
                }
                subtemas_lista.append(subtema_obj)

                tema_obj = {
                    "nome": tema_principal_str,
                    "subtemas": subtemas_lista
                }
                temas_lista.append(tema_obj)
                
                dia_obj = {
                    "semana": chave_semana,
                    "nome": dia_str,
                    "temas": temas_lista
                }
                
                # Adiciona o dia ao dicionário principal, agrupando por area_conhecimento
                # O defaultdict 'dados_brutos' garante que a lista para a área já existe
                dados_brutos[area_conhecimento_str].append(dia_obj)

        except Exception as e:
            print(f"Erro ao processar o arquivo {arquivo}: {e}")
            return {} # Retorna vazio se houver um erro de leitura

    return formatar_cronograma_final(dados_brutos)

def formatar_cronograma_final(dados_brutos):
    """
    Consolida as listas de dias para cada área e remove entradas duplicadas.
    """
    cronograma_ordenado = {}
    
    for area_conhecimento, dias_lista in dados_brutos.items():
        # Usa um set para rastrear dias já vistos e evitar duplicatas
        dias_processados = {} # Usamos um dicionário para consolidar temas e subtemas
        
        for dia in dias_lista:
            dia_key = dia['nome']
            if dia_key not in dias_processados:
                dias_processados[dia_key] = {
                    "semana": dia['semana'],
                    "nome": dia['nome'],
                    "temas": defaultdict(lambda: {
                        "nome": "",
                        "subtemas": defaultdict(lambda: {
                            "nome": "",
                            "aulas": []
                        })
                    })
                }

            # Consolida temas e subtemas no mesmo dia
            for tema in dia['temas']:
                tema_key = tema['nome']
                if tema_key not in dias_processados[dia_key]['temas']:
                    dias_processados[dia_key]['temas'][tema_key]['nome'] = tema_key
                
                for subtema in tema['subtemas']:
                    subtema_key = subtema['nome']
                    if subtema_key not in dias_processados[dia_key]['temas'][tema_key]['subtemas']:
                        dias_processados[dia_key]['temas'][tema_key]['subtemas'][subtema_key]['nome'] = subtema_key
                    
                    for aula in subtema['aulas']:
                        if aula not in dias_processados[dia_key]['temas'][tema_key]['subtemas'][subtema_key]['aulas']:
                             dias_processados[dia_key]['temas'][tema_key]['subtemas'][subtema_key]['aulas'].append(aula)

        
        # Converte a estrutura de volta para listas
        dias_finais = list(dias_processados.values())
        for dia_final in dias_finais:
            temas_lista = []
            for tema_obj in dia_final['temas'].values():
                subtemas_lista = list(tema_obj['subtemas'].values())
                tema_obj['subtemas'] = subtemas_lista
                temas_lista.append(tema_obj)
            dia_final['temas'] = temas_lista
            
        cronograma_ordenado[area_conhecimento] = dias_finais
    
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
    Retorna toda a estrutura do cronograma como um dicionário de áreas de conhecimento.
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
    for area_conhecimento, dias in cronograma_final.get("cronograma", {}).items():
        # Constrói uma string com os dados da area de conhecimento para busca
        area_busca = area_conhecimento.lower()

        if termo in area_busca:
             # Se o termo for encontrado na area, adiciona todos os dias
             for dia in dias:
                 resultados.append({
                    "semana": dia['semana'],
                    "dia": dia['nome'],
                    "area_conhecimento": area_conhecimento,
                    "temas": [t for t in dia.get('temas', [])],
                    "aula_encontrada": []
                 })
             continue
        
        for dia in dias:
            dia_busca = f"{dia['nome']}".lower()
            if termo in dia_busca:
                resultados.append({
                    "semana": dia['semana'],
                    "dia": dia['nome'],
                    "area_conhecimento": area_conhecimento,
                    "temas": [t for t in dia.get('temas', [])],
                    "aula_encontrada": []
                })
                continue
            for tema in dia.get("temas", []):
                for subtema in tema.get("subtemas", []):
                    for aula in subtema.get("aulas", []):
                        # Constrói uma string de busca com todo o caminho
                        caminho_completo = f"{area_busca} {dia['nome']} {tema['nome']} {subtema['nome']} {aula['nome']}".lower()
                        if termo in caminho_completo:
                            resultados.append({
                                "area_conhecimento": area_conhecimento,
                                "semana": dia['semana'],
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
print("Processando arquivos do cronograma...")
cronograma_final = processar_arquivos_para_hierarquia()

if __name__ == '__main__':
    if cronograma_final.get("cronograma"):
        num_areas = len(cronograma_final.get("cronograma", {}))
        if num_areas > 0:
            print(f"Processamento concluído. {num_areas} áreas carregadas.")
            print("API pronta para receber requisições.")
        else:
            print("Nenhum dado de cronograma foi carregado. O arquivo pode estar vazio ou com formato incorreto.")
    else:
        print("Erro: A função de processamento de arquivos não retornou o dicionário esperado.")

    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
