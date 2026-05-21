import sqlite3
import os

def verify_database(db_path: str):
    """Verifica e exibe um relatório completo das tabelas e entradas de um banco SQLite."""
    
    if not os.path.exists(db_path):
        print(f"❌ Erro: O arquivo '{db_path}' não foi encontrado.")
        print("Verifique se o script está na mesma pasta que o banco de dados ou ajuste o caminho.")
        return

    print(f"\n🔍 Analisando banco de dados: {db_path}")
    print("=" * 50)
    
    try:
        conn = sqlite3.connect(db_path)
        # Configura o row_factory para podermos extrair os nomes das colunas como dicionários
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Busca todas as tabelas (ignorando as tabelas internas do SQLite)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row['name'] for row in cursor.fetchall()]

        if not tables:
            print("⚠️ O banco de dados existe, mas está oco (não possui nenhuma tabela).")
            return

        for table in tables:
            # Conta o total de registros na tabela
            cursor.execute(f"SELECT COUNT(*) as total FROM {table}")
            total_rows = cursor.fetchone()['total']
            
            print(f"\n📂 Tabela: '{table}'")
            print(f"📊 Total de Registros: {total_rows}")
            
            # Se a tabela tiver dados, exibe uma amostra
            if total_rows > 0:
                print("📌 Amostra (3 primeiros registros):")
                cursor.execute(f"SELECT * FROM {table} LIMIT 3")
                sample_rows = cursor.fetchall()
                
                for i, row in enumerate(sample_rows, 1):
                    # Converte a linha para dicionário para uma impressão limpa
                    row_data = dict(row)
                    
                    # Trunca campos de texto muito longos (como descrições) para não sujar o terminal
                    for key, value in row_data.items():
                        if isinstance(value, str) and len(value) > 60:
                            row_data[key] = value[:57] + "..."
                            
                    print(f"   {i}. {row_data}")
            else:
                print("📌 Status: Vazia")

        print("\n" + "=" * 50)
        print("✅ Relatório gerado com sucesso!\n")

    except sqlite3.Error as e:
        print(f"❌ Erro ao ler o banco de dados: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    # Caminho do banco de dados. 
    # Se o script estiver na mesma pasta que o .db, use apenas 'bot_database.db'.
    # Se estiver fora, mude para '../bot_database.db' ou o caminho absoluto.
    CAMINHO_DB = 'bot_database.db'
    
    verify_database(CAMINHO_DB)