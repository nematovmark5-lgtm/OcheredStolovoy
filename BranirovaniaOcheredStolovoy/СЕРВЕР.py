from flask import Flask, request, jsonify
import mysql.connector
from datetime import datetime
from flask_cors import CORS



app = Flask(__name__)
CORS(app)

# Подключение к базе данных
def get_db_connection():
    try:
        return mysql.connector.connect(
            host='localhost',
            user='Mark',
            password='0987654321',
            database='stolovaya'
        )
    except mysql.connector.Error as err:
        print(f"Ошибка подключения к базе данных: {err}")
        return None


# Получить следующий номер заказа (всегда смотрит актуальное состояние базы)
def get_next_order_number():
    conn = get_db_connection()
    if conn is None:
        return 100  # Если нет подключения, начинаем с 100
        
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(number_order) FROM orders')
        result = cursor.fetchone()
        
        # Если заказов нет, начинаем с 100
        if result[0] is None:
            return 100
        
        # Находим следующий свободный номер, начиная с 100
        cursor.execute('''
            SELECT MIN(t1.number_order + 1) AS next_available
            FROM orders t1
            WHERE NOT EXISTS (
                SELECT 1 FROM orders t2 
                WHERE t2.number_order = t1.number_order + 1
            ) AND t1.number_order >= 99
            UNION
            SELECT 100
            WHERE NOT EXISTS (SELECT 1 FROM orders WHERE number_order >= 100)
            ORDER BY next_available
            LIMIT 1
        ''')
        
        next_available = cursor.fetchone()
        
        if next_available and next_available[0] is not None:
            return next_available[0]
        else:
            # Если все номера заняты, берем максимальный + 1
            return result[0] + 1
            
    except mysql.connector.Error as err:
        print(f"Ошибка получения номера заказа: {err}")
        return 100
    finally:
        if conn:
            conn.close()

@app.route('/api/last_order', methods=['GET'])
def get_last_order():
    try:
        next_order = get_next_order_number()
        
        # Находим последний существующий заказ
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT MAX(number_order) FROM orders')
                last_order = cursor.fetchone()[0] or 0
            finally:
                conn.close()
        else:
            last_order = 0
        
        return jsonify({
            'last_order': last_order,
            'next_order': next_order
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/order', methods=['POST'])
def create_order():
    try:
        data = request.get_json()
        if not data or 'food' not in data or 'drink' not in data:
            return jsonify({'error': 'Неверные данные'}), 400
            
        food = data['food']
        drink = data['drink']
        
        # Получаем следующий номер заказа (всегда актуальный)
        order_number = get_next_order_number()
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO orders (number_order, food, drink, status) VALUES (%s, %s, %s, %s)',
                (order_number, food, drink, 'Готовится')
            )
            conn.commit()
            
            return jsonify({
                'message': 'Order saved successfully!',
                'order_number': order_number,
                'status': 'Готовится'
            }), 200
        except mysql.connector.Error as err:
            conn.rollback()
            return jsonify({'error': f'Ошибка базы данных: {err}'}), 500
        finally:
            if conn:
                conn.close()
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders', methods=['GET'])
def get_orders():
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT number_order, food, drink, status, order_time FROM orders ORDER BY number_order DESC')
            orders = cursor.fetchall()
            
            for order in orders:
                if order['order_time'] and isinstance(order['order_time'], datetime):
                    order['order_time'] = order['order_time'].isoformat()
            
            return jsonify(orders), 200
        except mysql.connector.Error as err:
            return jsonify({'error': f'Ошибка базы данных: {err}'}), 500
        finally:
            if conn:
                conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint для монитора кухни
@app.route('/api/kitchen_orders', methods=['GET'])
def get_kitchen_orders():
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify([]), 200
            
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute('''
                SELECT number_order, food, drink, status, order_time 
                FROM orders 
                WHERE status != 'Выполнен'
                ORDER BY order_time DESC
            ''')
            orders = cursor.fetchall()
            
            for order in orders:
                if order['order_time'] and isinstance(order['order_time'], datetime):
                    order['order_time'] = order['order_time'].isoformat()
            
            return jsonify(orders), 200
        except mysql.connector.Error as err:
            print(f"Ошибка базы данных: {err}")
            return jsonify([]), 200
        finally:
            if conn:
                conn.close()
    except Exception as e:
        print(f"Общая ошибка: {e}")
        return jsonify([]), 200

@app.route('/api/mark_ready', methods=['POST'])
def mark_as_ready():
    try:
        data = request.get_json()
        if not data or 'order_number' not in data:
            return jsonify({'error': 'Неверные данные'}), 400
            
        order_number = data['order_number']
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
        try:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE orders SET status = %s WHERE number_order = %s',
                ('Готово', order_number)
            )
            conn.commit()
            return jsonify({'message': 'Order marked as ready'}), 200
        except mysql.connector.Error as err:
            conn.rollback()
            return jsonify({'error': f'Ошибка базы данных: {err}'}), 500
        finally:
            if conn:
                conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint для удаления заказа
@app.route('/api/complete_order', methods=['POST'])
def complete_order():
    try:
        data = request.get_json()
        if not data or 'order_number' not in data:
            return jsonify({'error': 'Неверные данные'}), 400
            
        order_number = data['order_number']
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({'error': 'Ошибка подключения к базе данных'}), 500
            
        try:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM orders WHERE number_order = %s',
                (order_number,)
            )
            conn.commit()
            
            if cursor.rowcount > 0:
                return jsonify({'message': 'Order completed and deleted successfully'}), 200
            else:
                return jsonify({'error': 'Order not found'}), 404
                
        except mysql.connector.Error as err:
            conn.rollback()
            return jsonify({'error': f'Ошибка базы данных: {err}'}), 500
        finally:
            if conn:
                conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Добавляем endpoint для проверки здоровья сервера
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Server is running'}), 200

# Страница монитора кухни
@app.route('/kitchen')
def kitchen_monitor():
    with open('kitchen_monitor.html', 'r', encoding='utf-8') as f:
        return f.read()



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
