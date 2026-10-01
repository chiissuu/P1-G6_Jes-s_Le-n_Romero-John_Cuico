__author__ = 'Pablo Ramos Criado'
__students__ = 'John Cuico y Jesús León' 

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import time
from typing import Generator, Any, Self
from geojson import Point
import pymongo
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from bson.objectid import ObjectId
import yaml

def getLocationPoint(address: str) -> Point:
    """ 
    Obtiene las coordenadas de una dirección en formato geojson.Point
    Utilizar la API de geopy para obtener las coordenadas de la direccion
    Cuidado, la API es publica tiene limite de peticiones, utilizar sleeps.

    Parameters
    ----------
        address : str
            direccion completa de la que obtener las coordenadas
    Returns
    -------
        geojson.Point
            coordenadas del punto de la direccion
    """
    location = None
    intentos = 0
    maxIntentos = 5
    while location is None and intentos < maxIntentos:
        intentos += 1
        try:
            time.sleep(1)
            #TODO
            # Es necesario proporcionar un user_agent para utilizar la API
            # Utilizar un nombre aleatorio para el user_agent
            location = Nominatim(user_agent="g6-utad").geocode(address)
        except GeocoderTimedOut:
            # Puede lanzar una excepcion si se supera el tiempo de espera
            # Volver a intentarlo
            continue
    #TODO
    if(location == None):
        raise ValueError("No se pudieron obtener coordenadas")
    return Point((location.longitude, location.latitude))
    # Devolver un GeoJSON de tipo punto con la latitud y longitud almacenadas.
    # Si no se consiguieron coordenadas, lanzar ValueError: la funcion no puede
    # devolver un punto inventado ni None silenciosamente. Es lo que espera la
    # prueba test_get_location_point_timeout_failure.

class Model:
    """ 
    Clase de modelo abstracta
    Crear tantas clases que hereden de esta clase como  
    colecciones/modelos se deseen tener en la base de datos.
    Model es la clase que tiene el comportamineto base de cada Coleccion.

    Mondo db frente a BD relacional
    -----
    Colección -> Tabla
    Documento -> Fila
    Campo -> Columna

    Ej Documento: 
    {
        "_id": "...",
        "nombre": "WiZink Center",
        "direccion": "Avenida de Felipe II, Madrid",
        "aforo": 17000,
        "servicios": ["aparcamiento", "guardarropa"]
    }
    Luego una coleccion seran varios documentos, haciendo una tabla.

    Base de datos: abd
    Colección: Recinto
    Clase Python: Recinto(Model)
    Objeto Python: recinto1
    Documento MongoDB: datos de un recinto concreto

    Attributes
    ----------
        required_vars : set[str]
            conjunto de atributos requeridos por el modelo
        admissible_vars : set[str]
            conjunto de atributos admitidos por el modelo
        db : pymongo.collection.Collection
            conexion a la coleccion de la base de datos
    -----------
        _required_vars   → campos que deben aparecer
        _admissible_vars → campos opcionales permitidos
        _db              → colección concreta de MongoDB
        _location_var    → campo que contiene la dirección
        _internal_vars   → variables internas que no se guardan como datos
        _data            → datos concretos de cada objeto
        _modified_vars   → campos que el objeto ha modificado
        _id              → identidad del documento en MongoDB, (LO AÑADIMOS NOSOTROS, no estaba antes, Evita que id termine dentro de data.)
         
    
    Methods
    -------
        __setattr__(name: str, value: str | dict) -> None
            Sobreescribe el metodo de asignacion de valores a los 
            atributos del objeto con el fin de controlar qué atributos 
            son modificados y cuando son modificados.
        __getattr__(name: str) -> Any
            Sobreescribe el metodo de acceso a atributos del objeto 
        save()  -> None
            Guarda el modelo en la base de datos
        delete() -> None
            Elimina el modelo de la base de datos
        find(filter: dict[str, str | dict]) -> ModelCursor
            Realiza una consulta de lectura en la BBDD.
            Devuelve un cursor de modelos ModelCursor
        aggregate(pipeline: list[dict]) -> pymongo.command_cursor.CommandCursor
            Devuelve el resultado de una consulta aggregate.
        find_by_id(id: str) -> dict | None
            Busca un documento por su id utilizando la cache y lo devuelve.
            Si no se encuentra el documento, devuelve None.
        init_class(db_collection: pymongo.collection.Collection, required_vars: set[str], admissible_vars: set[str]) -> None
            Inicializa las variables de clase en la inicializacion del sistema.

    """
    _required_vars: set[str]
    _admissible_vars: set[str]
    _location_var: str | None = None
    _db: pymongo.collection.Collection

    # Importante!: nosotros añadimos el atributo _id a nuestras variables internas para que __setattr__ lo almacene 
    # directamente en el objeto y no dentro de _data.Este atributo identifica el documento en MongoDB y no debe
    # validarse ni actualizarse como un campo normal.
    _internal_vars: set[str] = frozenset(('_id','_modified_vars', '_required_vars', '_admissible_vars', '_db', '_data', '_location_var'))

    def __init__(self, **kwargs: dict[str, str | dict | list]) -> None:
        """
        Inicializa el modelo con los valores proporcionados en kwargs
        Comprueba que los valores proporcionados en kwargs son admitidos
        por el modelo y que las atributos requeridos son proporcionadas.

        -> None, este metodo no devuelve ningun valor. El trabajod e esta función es inicializar el objeto preparando sus atribuos.

        Parameters
        ----------
            self, el objeto concreto que se está construyendo. Por ejemlo a "Recinto"
            kwargs : dict[str, str | dict]
                diccionario con los valores de las atributos del modelo
            **kwargs, Recoge todos los argumentos con nombre que no estén declarados individualmente y guárdalos en un diccionario
        """

        # 1 · Inicializar las variables internas

        # Se crea dentro del objeto actual (self) el atributo (_data).
        # [str, str | dict | list], Las claves serán textos y los valores podrán ser textos, diccionarios o listas.
        # Se inicializa vacio = {}
        self._data: dict[str, str | dict | list] = {}

        # Se crea dentro del objeto actual (self) el atributo (_modified_vars).
        # set[str], Las variables seran texto.
        # Se inicializa vacio mediante = set().
        self._modified_vars: set[str] = set()

        # Se busca "_id" dentro de kwargs, luego si existe lo extrae y lo guarda en self_id. 
        # Eliminandolo finalmente de kwargs. Si no existe utiliza None.
        if "_id" in kwargs:
            document_id = kwargs["_id"]
            del kwargs["_id"]
        else:
         document_id = None
     
        # Se crea dentro del objeto actual (self) el atributo (_id) que hemos añadido nosotros extra.
        # Si document_id es None o ObjectId que
        self._id: ObjectId | None = document_id

        # 2 · Obtener las claves de kwargs y almacenarlas en una variable:

        # Se crea la variable temporal "received_vars" para esta función.
        # Variable que se va a utilizar para almacenar las variables que se han enviado en el kwargs.
        received_vars = set(kwargs)

        # 3 · Avisar de los campos obligatorios de "received_vars" que no estan:

        # Vamos a definir la variable temporal "missing_vars" para esta función.
        # Variable que se va a utilizar para comprobar si la diferencia entre las claves del diccionario de 
        # las variables requeridas y las recibidas mediante kwargs. 
        # Todos los campos obligatorios deben estar incluidos en los campos recibidos.    
        missing_vars = self._required_vars - received_vars       

        # Lo que hacemos ahora es comporbar si en missing_vars ha quedado algo, en el caso
        # en que haya quedado algo que sera la variable que falta, lanzara uan excepcion de tipo ValueError mandando la variable que falta.
        # Ya que lo correcto es que las dos variables "required_vars" y "received_vars"
        # sean de la misma longitud y tengan las mismas claves para que se puedan procesar los datos.
        if missing_vars:
            missing_text = ", ".join(sorted(missing_vars))
            raise ValueError(
                f"Faltan atributos obligatorios: {missing_text}"
            )

        # 4 · Avisar de los campos no permitidos.

        # Vamos a alamacenar en una sola variable temporal todos las variables requeridas y admisibles del modelo.
        # Con | lo que se hace es hacer una union de los dos conjuntos de variables.
        allowed_vars = self._required_vars | self._admissible_vars

        # Almacenamos ahora en otra variable remporal la diferencia entre las variables recividas y las permitidas.
        # De esta forma si hemso recibido una variable que no existe en la diferencia quedará esta variable extra no permitida.
        invalid_vars = received_vars - allowed_vars

        # Como antes, si hay algun resto en la variable "invalid_vars", el condicionañ se activa
        # y se va a devolver una excepcion de tipo AtribiteError con un mensaje que avisa que no se permite
        # la variable del resto que no esta entre las nuestras.
        if invalid_vars:
            invalid_text = ", ".join(sorted(invalid_vars))
            raise AttributeError(
                f"Atributos no admitidos: {invalid_text}"
            )

        # 5 · Guardar todos los datos validos.

        # Una vez validados, se copian en _data los campos recibidos
        # para este objeto/documento.
        self._data.update(kwargs)


        

    def __setattr__(self, name: str, value: str | dict) -> None:
        """ Sobreescribe el metodo de asignacion de valores a los 
        atributos del objeto con el fin de controlar que atributos 
        son modificados y cuando son modificados.
        """
        if name in self._internal_vars:
            super().__setattr__(name, value)
            return
        #TODO
        # Realizar las comprabociones y gestiones necesarias
        # antes de la asignacion.

        # Asigna el valor value a la variable name
        self._data[name] = value

    def __getattr__(self, name: str) -> Any:
        """ Sobreescribe el metodo de acceso a atributos del objeto
        __getattr__ solo es llamado cuando no encuentra el atributo
        en el objeto 
        """
        if name in self._internal_vars:
            return super().__getattribute__(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError
        
    def save(self) -> None:
        """
        Guarda el modelo en la base de datos
        Si el modelo no existe en la base de datos, se crea un nuevo
        documento con los valores del modelo. En caso contrario, se
        actualiza el documento existente con los nuevos valores del
        modelo.
        """
        #TODO
        pass #No olvidar eliminar esta linea una vez implementado

    def delete(self) -> None:
        """
        Elimina el modelo de la base de datos
        """
        #TODO
        pass
    
    @classmethod
    def find(cls, filter: dict[str, str | dict]) -> Any:
        """ 
        Utiliza el metodo find de pymongo para realizar una consulta
        de lectura en la BBDD.
        find debe devolver un cursor de modelos ModelCursor

        Parameters
        ----------
            filter : dict[str, str | dict]
                diccionario con el criterio de busqueda de la consulta
        Returns
        -------
            ModelCursor
                cursor de modelos
        """ 
        #TODO
        # cls es el puntero a la clase
        pass #No olvidar eliminar esta linea una vez implementado

    @classmethod
    def aggregate(cls, pipeline: list[dict]) -> pymongo.command_cursor.CommandCursor:
        """ 
        Devuelve el resultado de una consulta aggregate. 
        No hay nada que hacer en esta funcion.
        Se utilizara para las consultas solicitadas
        en el segundo proyecto de la practica.

        Parameters
        ----------
            pipeline : list[dict]
                lista de etapas de la consulta aggregate 
        Returns
        -------
            pymongo.command_cursor.CommandCursor
                cursor de pymongo con el resultado de la consulta
        """ 
        return cls._db.aggregate(pipeline)
    
    @classmethod
    def find_by_id(cls, id: str) -> Self | None:
        """ 
        NO IMPLEMENTAR HASTA EL TERCER PROYECTO
        Busca un documento por su id utilizando la cache y lo devuelve.
        Si no se encuentra el documento, devuelve None.

        Parameters
        ----------
            id : str
                id del documento a buscar
        Returns
        -------
            Self | None
                Modelo del documento encontrado o None si no se encuentra
        """ 
        #TODO
        pass

    @classmethod
    def init_class(cls, db_collection: pymongo.collection.Collection, indexes:dict[str,str], required_vars: set[str], admissible_vars: set[str]) -> None:
        """ 
        Inicializa los atributos de clase en la inicializacion del sistema.
        Aqui se deben inicializar o asegurar los indices. Tambien se puede
        alguna otra inicialización/comprobaciones o cambios adicionales
        que estime el alumno.

        Parameters
        ----------
            db_collection : pymongo.collection.Collection
                Conexion a la collecion de la base de datos.
            indexes: Dict[str,str]
                Set de indices y tipo de indices para la coleccion
            required_vars : set[str]
                Set de atributos requeridos por el modelo
            admissible_vars : set[str] 
                Set de atributos admitidos por el modelo
        """
        cls._db = db_collection
        cls._required_vars = required_vars
        cls._admissible_vars = admissible_vars
        # TODO
        # Recorrer indexes y crear cada índice segun su tipo: 'unique', 'asc'
        # y 'geosphere'. Comparar el tipo por igualdad, no con el operador 'in'.
        # Ojo con el índice geoespacial: save() guarda el GeoJSON Point en
        # <campo>_loc, luego el índice 2dsphere va sobre <campo>_loc, mientras
        # que _location_var debe guardar el nombre del campo base.


class ModelCursor:
    """ 
    Cursor para iterar sobre los documentos del resultado de una
    consulta. Los documentos deben ser devueltos en forma de objetos
    modelo.

    Attributes
    ----------
        model_class : Model
            Clase para crear los modelos de los documentos que se iteran.
        cursor : pymongo.cursor.Cursor
            Cursor de pymongo a iterar

    Methods
    -------
        __iter__() -> Generator
            Devuelve un iterador que recorre los elementos del cursor
            y devuelve los documentos en forma de objetos modelo.
    """

    def __init__(self, model_class: Model, cursor: pymongo.cursor.Cursor):
        """
        Inicializa el cursor con la clase de modelo y el cursor de pymongo

        Parameters
        ----------
            model_class : Model
                Clase para crear los modelos de los documentos que se iteran.
            cursor: pymongo.cursor.Cursor
                Cursor de pymongo a iterar
        """
        self.model = model_class
        self.cursor = cursor
    
    def __iter__(self) -> Generator:
        """
        Devuelve un iterador que recorre los elementos del cursor
        y devuelve los documentos en forma de objetos modelo.
        Utilizar yield para generar el iterador
        Utilizar la funcion next para obtener el siguiente documento del cursor
        Utilizar alive para comprobar si existen mas documentos.
        """
        #TODO
        pass #No olvidar eliminar esta linea una vez implementado

    '''
    --------------
    Orden de ejecución real
    1. initApp()
    ↓
    2. Lee models.yml
    ↓
    3. Crea las clases Recinto, Artista, Evento y Asistente
    ↓
    4. init_class() configura cada clase
    ↓
    5. Más adelante se crea un objeto
    ↓
    6. Model.__init__() valida sus datos
    '''

def initApp(definitions_path: str = "./models.yml", mongodb_uri="mongodb://localhost:27017/", db_name="abd", scope=globals()) -> None:
    """ 
    Declara las clases que heredan de Model para cada uno de los 
    modelos de las colecciones definidas en definitions_path.
    Inicializa las clases de los modelos proporcionando los indices y 
    atributos admitidos y requeridos para cada una de ellas y la conexión a la
    collecion de la base de datos.
    
    Parameters
    ----------
        definitions_path : str
            ruta al fichero de definiciones de modelos
        mongodb_uri : str
            uri de conexion a la base de datos
        db_name : str
            nombre de la base de datos
    """
    #TODO
    # Inicializar base de datos
    # LLamar al servidor con MongoClient porque ya están importadas la librerías de mongo arriba.
    # Mongoclient(direccion del servidor, version de Mongo Db que
    # sirve para que si se actualice Mongo siga funcionando)
    client = MongoClient(mongodb_uri, server_api = ServerApi('1'))
    # elegir la base dentro del servidor
    db = client[db_name]
    
    #TODO
    # Declarar tantas clases modelo colecciones existan en la base de datos
    # Leer el fichero de definiciones de modelos para obtener las colecciones,
    # indices y los atributos admitidos y requeridos para cada una de ellas.
    
    # Con open(ruta, .. ) abrimos el archivo en esa ruta y con el encoding = utf-8 es
    # para decirle como estan guardadas las letras para casos como la Ñ y tildes.
	# con "with as ... f" abrimos el archivo y lo llamamos f mientras lo usamos
    # se cierra solo al terminar el bloque
    with open(definitions_path, encoding="utf-8") as f:
        # guardamos en datos, le pasamos f que es el yaml y lo lee como si fuera un diccionario
        # y el safe_load es para que no ejecute nada raro que haya en el archivo escondido.
        datos  = yaml.safe_load(f)

	# declaramos dos variables nombre y config donde les metemos tantos diccionarios haya.
    # Ejemplo:  ("Recinto", {"required_vars": [...]})
    #           ("Artista", {"required_vars": [...]}) 
    # nombre = Recinto // config = la configuración de recinto 
    # así hasta terminar el bucle
    for nombre, config in datos.items():
        # Con type() creamos una clase nueva, que le pasamos el nombre que queremos y 
        # (Model,) es una lista que no se puede cambiar(tupla) y 
		# por ultimo un diccionario vacío {}
        # todo esto lo guadamos en una variable diccionario llamada scope recibida de la funcion.
        scope[nombre] = type(nombre, (Model,),{})    

	# Profe
    # Ejemplo de declaracion de modelo para colecion llamada MiModelo
    # scope["MiModelo"] = type("MiModelo", (Model,),{})
    # La clase se declara en tiempo de ejecucion y queda en scope, que no tiene
    # por que ser el espacio de nombres global: las pruebas le pasan su propio
    # diccionario. Por eso se inicializa a traves de scope y no por su nombre,
    # que ahi todavia no existe.
    # scope["MiModelo"].init_class(db_collection=None, indexes=None, required_vars=None, admissible_vars=None)

if __name__ == '__main__':
    
    # Inicializar base de datos y modelos con initApp
    #TODO
    initApp()

    #Ejemplo
    m = MiModelo(nombre="Pablo", apellido="Ramos", edad=18)
    m.save()
    m.nombre="Pedro"
    print(m.nombre)

    # Hacer pruebas para comprobar que funciona correctamente el modelo
    #TODO
    # Crear modelo

    # Asignar nuevo valor a variable admitida del objeto 

    # Asignar nuevo valor a variable no admitida del objeto 

    # Guardar

    # Asignar nuevo valor a variable admitida del objeto

    # Guardar

    # Buscar nuevo documento con find

    # Obtener primer documento

    # Modificar valor de variable admitida

    # Guardar