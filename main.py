import apache_beam as beam
from apache_beam.io import ReadFromText, WriteToText
from apache_beam.options.pipeline_options import PipelineOptions


def texto_para_lista(elemento, delimitador='|'):
    """
    Recebe um texto e um delimitador
    Retorna uma lista de elementos pelo delimitador
    """
    return elemento.split(delimitador)

def lista_para_dicionario(elemento, colunas):
    return dict(zip(colunas, elemento))

def trata_data(elemento, datecol):
    """
    Recebe um dicionario e cria um novo campo com ANO-MES
    Returna o mesmo dicionario com o novo campo
    """
    elemento['ano_mes'] = '-'.join(elemento[datecol].split('-')[:2])
    return elemento

def chave_uf(elemento):
    """
    Recebe um dicionario e retorna uma tupla com o estado (UF) e o elemento (UF, dicionario)
    """
    chave = elemento['uf']
    return (chave, elemento)

def is_float(num):
    try:
        float(num)
        return True
    except:
        return False

def casos_dengue(elemento):
    """
    Recebe uma tupla ('RS', [{}, {}])
    Retorna uma tupla ('RS-2014-12', 8.0)
    """
    uf, registros = elemento
    for registro in registros:
        if is_float(registro['casos']):
            casos = int(float(registro['casos']))
        else:
            casos = 0
        
        yield (f"{uf}-{registro['ano_mes']}", casos)

def chave_uf_ano_mes_de_lista(elemento):
    """
    Recebe uma lista de elementos
    Retorna uma tupla contento chave e qtde chuva mm
    ('UF-ANO-MES', 1.3)
    """
    data, mm, uf = elemento
    ano_mes = '-'.join(data.split('-')[:2])
    chave = f"{uf}-{ano_mes}"
    if float(mm) < 0:
        mm = 0.0
    else:
        mm = float(mm)
    return chave, mm

def chuvas(elemento):
    uf, registros = elemento
    for registro in registros:
        yield (f"{uf}-{registro['ano_mes']}", float(registro['mm']))

def arredonda(elemento):
    """
    Recebe uma tupla
    retorna uma tupla com o valor arredondado
    ('RO-2019-04', 950.8000000000028)
    ('RO-2019-04', 950.8)
    """
    chave, mm = elemento
    return chave, round(mm, 1)

def filtra_campos_vazios(elemento):
    """
    Remove elementos com chaves vazias
    recebe tupla 
    ('CE-2015-04', {'chuvas': [1973.0], 'dengue': [9292]})
    retorna tupla
    ('CE-2015-04', {'chuvas': [1973.0], 'dengue': [9292]})
    """
    chave, dados = elemento

    if all([
        dados['chuvas'],
        dados['dengue']
    ]):
        return True
    return False

def descompactar_elementos(elemento):
    """
    Recebe uma tupla
    ('CE-2015-01', {'chuvas': [504.0], 'dengue': [1747]})
    retorna uma tupla
    ('CE','2015','01','504.0','1747')
    """
    chave, dados = elemento
    chuva = dados['chuvas'][0]
    dengue = dados['dengue'][0]
    uf, ano, mes = chave.split('-')
    
    return uf, ano, mes, str(chuva), str(dengue)

def preparar_csv(elemento, delimitador=';'):
    """
    Recebe uma tupla
    ('CE', 2015, 11, 11.8, 718)
    retorna uma string delimitada
    "CE;2015;11;11.8;718"
    """
    return f"{delimitador}".join(elemento)

pipeline_options = PipelineOptions()
pipeline = beam.Pipeline(options=pipeline_options)

colunas_dengue = 'id|data_iniSE|casos|ibge_code|cidade|uf|cep|latitude|longitude'.split('|')
colunas_chuvas = 'data,mm,uf'.split(',')

dengue = (
    pipeline
    | "Leitura do dataset de dengue" >> 
        ReadFromText('sample_casos_dengue.txt', skip_header_lines=1)
    | "dengue De texto para lista" >> beam.Map(texto_para_lista)
    | "Converte dengue para dicionario" >> 
        beam.Map(lista_para_dicionario, colunas_dengue)
    | "Cria campo ano-mes" >> beam.Map(trata_data, 'data_iniSE')
    | "Cria chave pelo estado" >> beam.Map(chave_uf)
    | "Agrupa pela chave (estado)" >> beam.GroupByKey()
    | "Descompacta casos dedengue" >> beam.FlatMap(casos_dengue)
    | "Soma qtde de casos por chave (estado-ano-mes)" >> beam.CombinePerKey(sum)
    # | "Mostrar resultados" >> beam.Map(print)
)

chuvas = (
    pipeline
    | "Leitura do dataset de chuvas" >> 
        ReadFromText('sample_chuvas.csv', skip_header_lines=1)
    | "chuvas De texto para lista" >> beam.Map(texto_para_lista, ',')
    | "Cria chave uf-ano-mes" >> beam.Map(chave_uf_ano_mes_de_lista)
    | "Soma qtde de chuva por chave (estado-ano-mes)" >> beam.CombinePerKey(sum)
    | "Arredondar resultadors de chuvas" >> beam.Map(arredonda)
    # | "Mostrar chuvas resultados" >> beam.Map(print)
)

resultado = (
    # (chuvas,dengue)
    # | "Empilha as pcols" >> beam.Flatten()
    # | "agrupa as pcols" >> beam.GroupByKey()
    ({'chuvas':chuvas, 'dengue':dengue})
    | 'Mesclar pcols' >> beam.CoGroupByKey()
    | 'Filtrar dados vazios' >> beam.Filter(filtra_campos_vazios)
    | 'Descompacter elementos' >> beam.Map(descompactar_elementos)
    | 'Prepara csv' >> beam.Map(preparar_csv)
    # | "Mostrar resultados final" >> beam.Map(print)
)

header = 'uf;ano;mes;chuva;dengue'

resultado | 'Criar arquivo CSV' >> WriteToText("resultado",
    file_name_suffix='.csv',
    header=header)

pipeline.run()

