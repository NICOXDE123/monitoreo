# app.py
import sqlite3
import pytz
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, Response
from flask_cors import CORS
import csv
import io

app = Flask(__name__)
CORS(app)  # Esto es para evitar problemas de comunicación entre el ESP32 y el servidor

# --- 1. CONFIGURAR LA BASE DE DATOS ---
def init_db():
    """Crea la tabla para guardar los datos si no existe."""
    conn = sqlite3.connect('sensor_data.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS datos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            temperatura REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- 2. PÁGINA WEB (EL PANEL DE CONTROL) ---
# Aquí va el código HTML/CSS/JS para el dashboard
HTML_PAGINA = '''-
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard de Temperatura ESP32</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; margin-top: 30px; background: #f0f2f5; }
        .container { background: white; width: 90%; max-width: 1000px; margin: 0 auto; padding: 20px; border-radius: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .temp { font-size: 3em; margin: 10px 0; transition: all 0.3s ease; }
        .temp-normal { color: #2ecc71; }
        .temp-fuera { color: #e74c3c; background-color: #ffe5e5; border-radius: 20px; padding: 5px 20px; display: inline-block; }
        .small { font-size: 0.9em; color: #777; }
        .chart-wrapper { overflow-x: auto; margin: 30px 0; border: 1px solid #ddd; border-radius: 10px; background: #fafafa; }
        .chart-wrapper canvas { min-width: 800px; height: 400px; width: auto; }
        .status { font-weight: bold; }
        .online { color: green; }
        .offline { color: red; }
        .alerta { margin-top: 10px; font-weight: bold; }
        button { background: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; margin-top: 10px; }
        button:hover { background: #2980b9; }
        .error-msg { color: red; font-size: 0.8em; margin-top: 10px; }

        @media (max-width: 768px) {

            .temp {
                font-size: 2.2em;
            }

            .container {
                padding: 15px;
            }

            .chart-wrapper canvas {
                min-width: 600px;
            }

        }

        @media (max-width: 480px) {

            .temp {
                font-size: 1.8em;
            }

            h1 {
                font-size: 1.4em;
            }

            button {
                width: 100%;
                margin-top: 10px;
            }

        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <h1> 🌡️ Monitor de Temperatura</h1>
        <div class="temp" id="temp-container">
            <span id="temp-valor">--</span> °C
        </div>
        <div id="alerta-texto" class="alerta"></div>
        <div class="small">
            Rango aceptable: <strong>18°C - 26°C</strong>
        </div>
        <div class="small">
            Última actualización: <span id="tiempo-actualizacion">--:--:--</span>
        </div>
        <div class="small">
            Estado: <span id="estado" class="offline">Esperando datos...</span>
        </div>
        
        <!-- Contenedor con scroll horizontal -->
        <div class="chart-wrapper">
            <canvas id="tempChart"></canvas>
        </div>
        <div class="small">
            📡 Últimas 20 mediciones (desliza hacia la derecha si hay más puntos)
        </div>
        <div class="d-flex gap-2 justify-content-center mt-3">
            <button id="refreshBtn" class="btn btn-primary">🔄 Actualizar gráfica</button>
            <button id="downloadCsvBtn" class="btn btn-success">📥 Descargar CSV</button>
        </div>
        <div id="errorMsg" class="error-msg"></div>
    </div>

    <script>
        let chart;
        let ultimaTemperatura = null;

        function initChart() {
            const ctx = document.getElementById('tempChart').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Temperatura (°C)',
                        data: [],
                        borderColor: '#e67e22',
                        backgroundColor: 'rgba(230, 126, 34, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 3,
                        pointHoverRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,  // Para que respete el alto fijo
                    scales: {
                        y: {
                            title: { display: true, text: 'Temperatura (°C)' },
                            min: 0,
                            max: 50
                        },
                        x: {
                            title: { display: true, text: 'Hora' },
                            ticks: { autoSkip: true, maxTicksLimit: 10 }
                        }
                    },
                    plugins: {
                        tooltip: { mode: 'index', intersect: false },
                        legend: { position: 'top' }
                    }
                }
            });
        }

        async function cargarHistorial() {
            try {
                const response = await fetch('/api/historial');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                console.log("Historial recibido:", data);
                
                if (!data || data.length === 0) {
                    document.getElementById('errorMsg').innerText = "Aún no hay datos históricos. Esperando al ESP32...";
                    return;
                }
                
                const labels = data.map(d => {
                    let fecha = new Date(d.timestamp);
                    return fecha.toLocaleTimeString();
                });
                const temps = data.map(d => d.temperatura);
                
                if (chart) {
                    chart.data.labels = labels;
                    chart.data.datasets[0].data = temps;
                    chart.update();
                    document.getElementById('errorMsg').innerText = "";
                }
            } catch (error) {
                console.error('Error cargando historial:', error);
                document.getElementById('errorMsg').innerText = "Error al cargar historial: " + error.message;
            }
        }

        function actualizarIndicador(temp) {
            const tempContainer = document.getElementById('temp-container');
            const alertaDiv = document.getElementById('alerta-texto');
            tempContainer.classList.remove('temp-normal', 'temp-fuera');
            
            if (temp < 18) {
                tempContainer.classList.add('temp-fuera');
                alertaDiv.innerHTML = '❌ Temperatura demasiado BAJA (menor a 18°C)';
                alertaDiv.style.color = '#e74c3c';
            } else if (temp > 26) {
                tempContainer.classList.add('temp-fuera');
                alertaDiv.innerHTML = '❌ Temperatura demasiado ALTA (superior a 26°C)';
                alertaDiv.style.color = '#e74c3c';
            } else {
                tempContainer.classList.add('temp-normal');
                alertaDiv.innerHTML = '✅ Temperatura dentro del rango aceptable';
                alertaDiv.style.color = '#2ecc71';
            }
        }

        async function cargarDatos() {
            try {
                const response = await fetch('/api/datos');
                if (!response.ok) throw new Error('Error en datos');
                const data = await response.json();
                
                if (data.temperatura !== undefined) {
                    const temp = data.temperatura;
                    document.getElementById('temp-valor').innerText = temp.toFixed(1);
                    document.getElementById('tiempo-actualizacion').innerText = new Date().toLocaleTimeString();

                    // Verificar si el dato es reciente (<= 15 segundos)
                    if (data.timestamp) {
                        const fechaDato = new Date(data.timestamp);
                        const ahora = new Date();
                        const diferencia = (ahora - fechaDato) / 1000; // en segundos

                        if (diferencia > 15) {
                            document.getElementById('estado').innerText = 'Offline';
                            document.getElementById('estado').className = 'status offline';
                        } else {
                            document.getElementById('estado').innerText = 'Online';
                            document.getElementById('estado').className = 'status online';
                        }
                    } else {
                        // Si no hay timestamp, mantenemos comportamiento previo
                        document.getElementById('estado').innerText = 'Online';
                        document.getElementById('estado').className = 'status online';
                    }

                    actualizarIndicador(temp);

                    if (ultimaTemperatura !== temp) {
                        ultimaTemperatura = temp;
                        cargarHistorial();
                    }
                } else {
                    document.getElementById('estado').innerText = 'Sin datos';
                    document.getElementById('estado').className = 'status offline';
                }
            } catch (error) {
                console.error('Error al cargar:', error);
                document.getElementById('estado').innerText = 'Desconectado';
                document.getElementById('estado').className = 'status offline';
            }
        }

        window.onload = () => {
            initChart();
            cargarHistorial();
            cargarDatos();
            setInterval(cargarDatos, 5000);
            setInterval(cargarHistorial, 30000);
            document.getElementById('refreshBtn').onclick = () => cargarHistorial();
            const dlBtn = document.getElementById('downloadCsvBtn');
            if (dlBtn) dlBtn.onclick = () => { window.location.href = '/api/exportar_csv'; };
        };
    </script>
</body>
</html>
'''
# --- 3. RUTAS DE LA API (DONDE EL ESP32 ENVÍA LOS DATOS) ---

@app.route('/api/temperatura', methods=['POST'])
def recibir_temperatura():
    """Recibe la temperatura desde el ESP32 y la guarda con hora local."""
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Datos inválidos"}), 400
        
        temperatura = data.get('temperatura')
        if temperatura is None:
            return jsonify({"error": "Falta el campo 'temperatura'"}), 400
        
        # Obtener hora local de Chile (Santiago)
        zona_chile = pytz.timezone('America/Santiago')
        hora_local = datetime.now(zona_chile)
        
        # Guardar en la base de datos
        conn = sqlite3.connect('sensor_data.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO datos (timestamp, temperatura) VALUES (?, ?)',
            (hora_local, temperatura)
        )
        conn.commit()
        conn.close()
        
        print(f"Datos guardados: {temperatura} °C a las {hora_local}")
        return jsonify({"message": "Datos recibidos correctamente", "temperatura": temperatura}), 200
    except Exception as e:
        print(f"Error al procesar: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/historial', methods=['GET'])
def obtener_historial():
    """Devuelve las últimas 20 temperaturas para la gráfica."""
    conn = sqlite3.connect('sensor_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT timestamp, temperatura FROM datos 
        ORDER BY timestamp DESC LIMIT 20
    ''')
    filas = cursor.fetchall()
    conn.close()
    
    # Invertir para que quede de más antigua a más reciente
    historial = []
    for fila in reversed(filas):
        historial.append({
            'timestamp': fila[0],
            'temperatura': fila[1]
        })
    return jsonify(historial)

@app.route('/api/datos', methods=['GET'])
def obtener_datos():
    """Devuelve el último dato guardado."""
    conn = sqlite3.connect('sensor_data.db')
    cursor = conn.cursor()
    cursor.execute('SELECT temperatura, timestamp FROM datos ORDER BY timestamp DESC LIMIT 1')
    ultimo = cursor.fetchone()
    conn.close()
    if ultimo:
        return jsonify({'temperatura': ultimo[0], 'timestamp': ultimo[1]})
    else:
        return jsonify({'error': 'No hay datos aún'}), 404


@app.route('/api/exportar_csv')
def exportar_csv():

    conn = sqlite3.connect('sensor_data.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, temperatura
        FROM datos
        ORDER BY timestamp DESC
    """)

    datos = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(['Fecha', 'Temperatura'])

    for fila in datos:
        writer.writerow(fila)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            "attachment; filename=temperaturas.csv"
        }
    )

@app.route('/')
def dashboard():
    """Muestra el panel de control."""
    # Aquí debes tener la variable HTML_PAGINA con todo el código HTML/JS
    return render_template_string(HTML_PAGINA)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)