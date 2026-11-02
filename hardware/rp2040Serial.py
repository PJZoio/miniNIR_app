"""
A library to interface Arduino through serial connection
https://pyserial.readthedocs.io/en/latest/shortintro.html

"""
import serial

class rp2040():
    """
    Models an Arduino Serial connection
    """

    def __init__(self, serial_port='/dev/ttyACM0', baud_rate=230400,
            read_timeout=20):
        """
        Initializes the serial connection to the Arduino board
        """
        self.ser = serial.Serial(serial_port, baud_rate)
        self.ser.timeout = read_timeout # Timeout for readline()

    def moveTo(self, motor_number, value):
        """
        Writes the digital_value on pin_number
        Internally sends b'WD{pin_number}:{digital_value}' over the serial
        connection
        """
        #command = (''.join(('MX ', str(motor_number), ' ',
        #command = (''.join(('MX ', ' ',
        #    str(value)))).encode()
        #Unicode strings must be encoded (e.g. 'hello'.encode('utf-8').
        command = f'M{motor_number} {value}\r\n'.encode('utf-8')
        print(command)
        self.ser.write(command)
        line = self.ser.readline()   # read a '\n' terminated line
        print(line)

    def close(self):
        """
        To ensure we are properly closing our connection to the
        Arduino device.
        """
        self.ser.close()
        print('Connection to RP2040 closed')

