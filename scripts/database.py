import psycopg2 as pg2

class DataBase:
    #Подключение
    def __init__(self, db_name, user, password, host):
        self.connection = pg2.connect(
            dbname=db_name,
            user=user,
            password=password,
            host=host,
        )
        self.cursor = self.connection.cursor()
        self.result = None

    #Добавляем запись
    def insert_database(self, query, params=None):
        try:
            self.cursor.execute(query, params)
            self.connection.commit()
        except Exception as ex:
            print(f"Ошибка - {ex}")
            return False  
        return True
        
    #Читаем запись
    def read_database(self, query, params=None):
        try:
            self.cursor.execute(query, params)
            self.connection.commit() 
            self.result = self.cursor.fetchall()

        except Exception as ex:
            print(f"Ошибка - {ex}")
        
        return self.result

    #Закрываем соединение
    def close_connect(self):
        if self.cursor is not None:
            self.cursor.close()
        elif self.connection is not None:
            self.connection.close()