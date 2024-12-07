from flask import Flask, render_template, request, send_file
import pdfplumber
import csv
import io
import re
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
UPLOAD_FOLDER = 'temp'
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILES = 12

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def print_debug(message):
    """Helper function to print debug messages"""
    print(f"DEBUG: {message}")

def extract_santander_transactions(pdf_path):
    """
    Extrai dados de transações de extratos do Banco Santander.
    """
    transactions = []
    print_debug(f"Processando ficheiro: {pdf_path}")
    
    with pdfplumber.open(pdf_path) as pdf:
        transaction_section = False
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            lines = text.split('\n')
            
            for line in lines:
                if "Detalhe de Movimentos da Conta à Ordem" in line:
                    transaction_section = True
                    continue
                
                if not transaction_section:
                    continue
                
                date_pattern = r'^(\d{2}[-/]\d{2})\s+(\d{2}[-/]\d{2})'
                date_match = re.match(date_pattern, line)
                
                if date_match:
                    try:
                        parts = line.split()
                        if len(parts) >= 4:
                            date_str = parts[0].replace('-', '/')
                            
                            balance = None
                            amount = None
                            for i in range(len(parts)-1, -1, -1):
                                if re.match(r'^-?[\d.,]+$', parts[i].replace('.', '').replace(',', '')):
                                    if balance is None:
                                        balance = float(parts[i].replace('.', '').replace(',', '.'))
                                    elif amount is None:
                                        amount = float(parts[i].replace('.', '').replace(',', '.'))
                                        break
                            
                            description = ' '.join(parts[2:-2])
                            
                            # Converter data para formato padrão
                            date = datetime.strptime(date_str + "/2024", '%d/%m/%Y')
                            
                            if amount is not None:
                                transactions.append({
                                    'date': date,
                                    'description': description,
                                    'amount': amount,
                                    'balance': balance
                                })
                    
                    except Exception as e:
                        print_debug(f"Erro ao processar linha: {line}")
                        print_debug(f"Detalhes do erro: {str(e)}")
                        continue
    
    print_debug(f"Foram encontradas {len(transactions)} transações")
    return transactions

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    if 'files[]' not in request.files:
        return render_template('index.html', error='Nenhum ficheiro carregado')
    
    files = request.files.getlist('files[]')
    print_debug(f"Recebidos {len(files)} ficheiros")
    
    if len(files) > MAX_FILES:
        return render_template('index.html', error=f'Máximo de {MAX_FILES} ficheiros permitidos')
    
    if not files or files[0].filename == '':
        return render_template('index.html', error='Nenhum ficheiro selecionado')
    
    all_transactions = []
    processed_files = 0
    
    try:
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                try:
                    transactions = extract_santander_transactions(filepath)
                    all_transactions.extend(transactions)
                    processed_files += 1
                finally:
                    # Remover o ficheiro carregado
                    if os.path.exists(filepath):
                        os.remove(filepath)
        
        if not all_transactions:
            return render_template('index.html', error='Não foram encontradas transações nos ficheiros carregados')
        
        # Ordenar as transações por data
        all_transactions.sort(key=lambda x: x['date'])
        
        # Converter objetos datetime para string no CSV
        for transaction in all_transactions:
            transaction['date'] = transaction['date'].strftime('%Y-%m-%d')
        
        # Criar CSV em memória
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['date', 'description', 'amount', 'balance'])
        writer.writeheader()
        writer.writerows(all_transactions)
        
        # Preparar o CSV para download
        mem = io.BytesIO()
        mem.write(output.getvalue().encode('utf-8'))
        mem.seek(0)
        output.close()
        
        print_debug(f"Processados {processed_files} ficheiros com um total de {len(all_transactions)} transações")
        
        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name='transacoes_santander.csv'
        )
            
    except Exception as e:
        print_debug(f"Erro durante o processamento: {str(e)}")
        return render_template('index.html', error=f'Erro ao processar os ficheiros: {str(e)}')

if __name__ == '__main__':
    app.run(debug=True)

