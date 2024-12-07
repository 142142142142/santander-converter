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
    Extract transaction data specifically from Santander bank statements.
    """
    transactions = []
    print_debug(f"Processing file: {pdf_path}")
    
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
                            
                            # Convert date to standard format
                            date = datetime.strptime(date_str + "/2024", '%d/%m/%Y')
                            
                            if amount is not None:
                                transactions.append({
                                    'date': date,
                                    'description': description,
                                    'amount': amount,
                                    'balance': balance
                                })
                    
                    except Exception as e:
                        print_debug(f"Error processing line: {line}")
                        print_debug(f"Error details: {str(e)}")
                        continue
    
    print_debug(f"Found {len(transactions)} transactions")
    return transactions

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    if 'files[]' not in request.files:
        return render_template('index.html', error='No files uploaded')
    
    files = request.files.getlist('files[]')
    print_debug(f"Received {len(files)} files")
    
    if len(files) > MAX_FILES:
        return render_template('index.html', error=f'Maximum {MAX_FILES} files allowed')
    
    if not files or files[0].filename == '':
        return render_template('index.html', error='No files selected')
    
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
                    # Clean up the uploaded file
                    if os.path.exists(filepath):
                        os.remove(filepath)
        
        if not all_transactions:
            return render_template('index.html', error='No transactions found in the uploaded files')
        
        # Sort all transactions by date
        all_transactions.sort(key=lambda x: x['date'])
        
        # Convert datetime objects to string format for CSV
        for transaction in all_transactions:
            transaction['date'] = transaction['date'].strftime('%Y-%m-%d')
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['date', 'description', 'amount', 'balance'])
        writer.writeheader()
        writer.writerows(all_transactions)
        
        # Prepare the CSV for download
        mem = io.BytesIO()
        mem.write(output.getvalue().encode('utf-8'))
        mem.seek(0)
        output.close()
        
        print_debug(f"Successfully processed {processed_files} files with {len(all_transactions)} total transactions")
        
        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name='santander_transactions.csv'
        )
            
    except Exception as e:
        print_debug(f"Error during processing: {str(e)}")
        return render_template('index.html', error=f'Error processing files: {str(e)}')

if __name__ == '__main__':
    app.run(debug=True)
