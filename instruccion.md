el archivo pollos_bebes.md contien datos de la siguiente estructura .

{
  "_id": {
    "$oid": "675c8d5bfd9f130e730072b8"
  },
  "set_point": 20,
  "temp_supply_1": 20.6,
  "return_air": 23.6,
  "evaporation_coil": 18.4,
  "condensation_coil": 38.2,
  "ambient_air": 23.7,
  "cargo_1_temp": 23,
  "cargo_2_temp": 22.5,
  "cargo_3_temp": 23.2,
  "cargo_4_temp": 22.8,
  "relative_humidity": 32766,
  "avl": 0,
  "co2_reading": 51,
  "o2_reading": 3276.6,
  "capacity_load": 4,
  "power_state": 0,
  "controlling_mode": "0",
  "created_at": {
    "$date": "2024-12-13T14:39:07.000Z"
  }
}


se entiende por set_point , el set de temeperatura programada que va de -40 a 40 .
temp_supply_1 la temperatura de suministro d el amaquina reefer que va de -40 a 40 
return_air la temperatura del sensor  de retorno que va de -40 a 40 

evaporation_coil la temperatura del evaporador que va de -40 a 40 

condensation_coil la temperatura del condensador que va de -40 a 40 


ambient_air la temperatura de ambiente exterior  que va de -10 a 50 

cargo_1_temp la temperatura de la zona uno que va de 5 a 50 grados 

cargo_2_temp la temperatura de la zona dos que va de 5 a 50 grados 

cargo_3_temp la temperatura de la zona tres que va de 5 a 50 grados 

cargo_4_temp la temperatura de la zona cuatro que va de 5 a 50 grados 

relative_humidity humedad relaitiva que va de 20 a 99 en %

avl  que es apertura d eventila que va de 0 a 230 cfm

co2_reading nivel de co2 en porcentaje que va de 0 a 24 %

o2_reading ivel de o2 en porcentaje que va de 0 a 24 %

capacity_load que es potencia de compresor de 0 a 100%

power_state que es estado on 1 y off 0

controlling_mode que es modo de funcionamiento

created_at que e sla fecha .


Todo o decrito es para limpiar la informacion que no corresponde de los sensores 

un aspecto mas , hay ocasiones que se lee 0 en return_air y temp_supply_1 esos datos se descartan son mala lectura .


El objetivo es crear un dashboard con la informacion con la informacion del archivo que permita navehar por dias los servicios , dadao que la infromacion es de un furgon refrigerado que transporta pollitos bebes de un punto a otro y normalmente demora horas , entonces que el programa procese la informacion detecte los dias de funcionamiento ,  el promedio de temepraturas , por zona , retorno suministro y permita comparar los datos por servicios realizados para ver si en un dia a otro hubo cambios significativos las zonadel 1 al 4 representa las zona sometidas a los pollitos . plantea una vista con un sistema compelto que comtemple esos obejtivos  , tambien los co2 que nos dira que tan ventilado estaba el ambiente interior , dado que a mas pollitos mas co2 en el interior del furgon 