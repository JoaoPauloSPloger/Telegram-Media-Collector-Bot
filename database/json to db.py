import json
import sqlite3
import os

def import_json_to_db(json_file_path: str, db_file_path: str):
    """Lê um arquivo JSON estruturado e injeta os dados em um banco SQLite."""
    
    if not os.path.exists(json_file_path):
        print(f"❌ Arquivo não encontrado: {json_file_path}")
        return

    # 1. Carrega o JSON forçando a codificação correta
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 2. Conecta ao banco de dados bruto
    conn = sqlite3.connect(db_file_path)
    cursor = conn.cursor()

    # 3. Itera sobre o dicionário (Tabelas -> Registros)
    for table_name, rows in data.items():
        print(f"Importando {len(rows)} registros na tabela '{table_name}'...")
        
        if not rows:
            continue
            
        for record in rows:
            # Extrai as colunas e prepara os placeholders (?)
            columns = ", ".join(record.keys())
            placeholders = ", ".join(["?"] * len(record))
            values = tuple(record.values())
            
            # Constrói dinamicamente a query. 
            # OR REPLACE garante que se o ID já existir, ele será atualizado sem travar o script.
            sql_query = f"INSERT OR REPLACE INTO {table_name} ({columns}) VALUES ({placeholders})"
            
            try:
                cursor.execute(sql_query, values)
            except sqlite3.OperationalError as e:
                print(f"⚠️ Erro ao inserir na tabela {table_name}: {e}")
                # Isso geralmente ocorre se o JSON tem uma tabela/coluna que ainda não existe no DB de destino

    # 4. Salva as alterações no disco e fecha
    conn.commit()
    conn.close()
    print("✅ Restauração do banco de dados concluída com sucesso!")

# Execução
# Como seu script está na pasta /database/, e o banco exportado também, os caminhos relativos são diretos:
import_json_to_db('database_export.json', '../bot_database.db')