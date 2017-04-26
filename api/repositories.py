import logging
import random
import string

from model import House, Room, User, Device, Thermostat, MotionSensor, LightSwitch, OpenSensor, Token


class Repository(object):
    def __init__(self, mongo_collection, repository_collection):
        self.collection = mongo_collection
        self.repositories = repository_collection

    def clear_db(self):
        self.collection.delete_many({})


class RepositoryCollection(object):
    def __init__(self, db):
        self.db = db
        self.user_repository = UserRepository(db.users, self)
        self.house_repository = HouseRepository(db.houses, self)
        self.room_repository = RoomRepository(db.rooms, self)
        self.device_repository = DeviceRepository(db.devices, self)
        self.trigger_repository = TriggerRepository(db.triggers, self)
        self.token_repository = TokenRepository(db.token, self)


class UserRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def update_user_account(self,user_id,name,password,house_name,house_location):
        user = self.get_user_by_id(user_id)
        if user is None:
            return None
        self.collection.update_one({'user_id': user_id, 'name': name,
                                    'password_hash': password, 'house_name': house_name,
                                    'house_location': house_location})

    def add_user(self, name, password_hash, email_address, is_admin):
        logging.debug("adding user!")
        existing_user = self.get_user_by_email(email_address)
        logging.debug("existing user: {}".format(existing_user))
        if existing_user is not None:
            raise Exception("There is already an account with this email.")
        user = self.collection.insert_one({'name': name, 'password_hash': password_hash,
                                           'email_address': email_address, 'is_admin': is_admin})
        return user.inserted_id

    def remove_user(self, user_id):
        self.collection.delete_one({'_id': user_id})

    def get_user_by_id(self, user_id):
        user = self.collection.find_one({'_id': user_id})
        if user is None:
            return None
        target_user = User(user)
        return target_user

    def get_user_by_email(self, email_address):
        logging.debug("All users: {}".format([x.email_address for x in self.get_all_users()]))
        user = self.collection.find_one({'email_address': email_address})
        if user is None:
            return None
        target_user = User(user)
        return target_user

    def get_all_users(self):
        users = self.collection.find()
        target_users = []
        for user in users:
            target_users.append(User(user))
        return target_users

    def faulty_user_devices(self, user_id):
        faulty_devs = DeviceRepository.get_faulty_devices()
        attributes = User.get_user_attributes(user_id)
        fault_check = False
        for device in faulty_devs:
            if device.user_id == user_id:
                fault_check = True
        attributes['faulty'] = fault_check
        return attributes


class HouseRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def add_house(self, user_id, name, location):
        user_houses = self.get_houses_for_user(user_id)
        for house in user_houses:
            other_name = house.name
            if name == other_name:
                raise Exception("There is already a house with this name.")
        house = self.collection.insert_one({'user_id': user_id, 'name': name})
        return house.inserted_id

    def remove_house(self, house_id):
        self.collection.delete_one({'_id': house_id})

    def get_house_by_id(self, house_id):
        house = self.collection.find_one({'_id': house_id})
        target_house = House(house)
        return target_house

    def get_houses_for_user(self, user_id):
        houses = self.collection.find({'user_id': user_id})
        target_houses = []
        logging.debug("Found {} houses".format(houses.count()))
        for house in houses:
            target_houses.append(House(house))
        return target_houses

    def get_all_houses(self):
        houses = self.collection.find()
        target_houses = []
        for house in houses:
            target_houses.append(House(house))
        return target_houses

    def validate_token(self, house_id, token):
        house = self.get_house_by_id(house_id)
        if house is None:
            return False
        else:
            user_id = house.user_id
            return self.repositories.token_repository.authenticate_user(user_id, token)


class RoomRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def add_room(self, house_id, name):
        house_rooms = self.get_rooms_for_house(house_id)
        for room in house_rooms:
            other_name = room.name
            if name == other_name:
                raise Exception("There is already a room with this name.")
        room = self.collection.insert_one({'house_id': house_id, 'name': name})
        return room.inserted_id

    def remove_room(self, room_id):
        self.collection.delete_one({'_id': room_id})

    def get_room_by_id(self, room_id):
        room = self.collection.find_one({'_id': room_id})
        target_room = Room(room)
        return target_room

    def get_rooms_for_house(self, house_id):
        rooms = self.collection.find({'house_id': house_id})
        target_rooms = []
        for room in rooms:
            target_rooms.append(Room(room))
        return target_rooms

    def get_all_rooms(self):
        rooms = self.collection.find()
        target_rooms = []
        for room in rooms:
            target_rooms.append(Room(room))
        return target_rooms

    def validate_token(self, room_id, token):
        room = self.get_room_by_id(room_id)
        if room is None:
            return False
        else:
            house_id = room.house_id
            return self.repositories.house_repository.validate_token(house_id, token)


class DeviceRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def get_faulty_devices(self):
        all_device_ids = [x['_id'] for x in self.collection.find({}, {})]
        devices = []
        for device_id in all_device_ids:
            device = self.get_device_by_id(device_id)
            if device.is_faulty():
                devices.append(device)
        return devices

    def update_device_reading(self, device):
        reading = device.read_current_state()
        logging.debug("Read current state of device {}: {}".format(device.get_device_id(), reading))
        self.collection.update_one({'_id': device.get_device_id()},
                                   {"$set": {'status': {"last_read": reading}}})

    def update_all_device_readings(self):
        all_device_ids = [x['_id'] for x in self.collection.find({}, {})]
        for device_id in all_device_ids:
            device = self.get_device_by_id(device_id)
            self.update_device_reading(device)

    def add_device(self, house_id, room_id, name, device_type, power_state, configuration, vendor):
        house_devices = self.get_devices_for_house(house_id)
        for device in house_devices:
            other_name = device.name
            if name == other_name:
                raise Exception("There is already a device with this name.")
        device = self.collection.insert_one({'house_id': house_id, 'room_id': room_id,
                                             'name': name, 'device_type': device_type,
                                             'power_state': power_state,
                                             'configuration': configuration,
                                             'vendor': vendor})
        device_id = device.inserted_id
        self.collection.update_one({'_id': device_id}, {"$set": {'status': {'last_read': 0}}})
        self.set_device_type(device_id)
        device = self.get_device_by_id(device_id=device_id)
        self.update_device_reading(device)
        return device_id

    def set_device_type(self, device_id):
        device = self.collection.find_one({'_id': device_id})
        if device['device_type'] == "thermostat":
            self.collection.update_one({'_id': device_id}, {"$set": {'target': {'locked_max_temperature': 50}}})
            self.collection.update_one({'_id': device_id}, {"$set": {'target': {'locked_min_temperature': 0}}})
            self.collection.update_one({'_id': device_id}, {"$set": {'temperature_scale': "C"}})
            self.collection.update_one({'_id': device_id}, {"$set": {'target': {'target_temperature': 25}}})
            self.collection.update_one({'_id': device_id}, {"$set": {'status': {'last_temperature': 0}}})
        elif device['device_type'] == "motion_sensor":
            self.collection.update_one({'_id': device_id}, {"$set": {'sensor_data': 0}})
        # elif device['device_type'] == "light_switch":
        elif device['device_type'] == "open_sensor":
            self.collection.update_one({'_id': device_id}, {"$set": {'sensor_data': 0}})

    def remove_device(self, device_id):
        #self.repositories.device_group_repository.remove_device_from_group(device_id)
        self.collection.delete_one({'_id': device_id})

    def get_device_by_id(self, device_id):
        device = self.collection.find_one({'_id': device_id})
        if device is None:
            return None
        device_type = device['device_type'] if 'device_type' in device else None
        if device_type == "thermostat":
            return Thermostat(device)
        elif device_type == "motion_sensor":
            return MotionSensor(device)
        elif device_type == "light_switch":
            return LightSwitch(device)
        elif device_type == "open_sensor":
            return OpenSensor(device)
        return Device(device)

    def add_device_to_house(self, house_id, device_id):
        self.collection.update_one({'_id': device_id}, {"$set": {'house_id': house_id}}, upsert=False)

    def get_devices_for_house(self, house_id):
        devices = self.collection.find({'house_id': house_id})
        target_devices = []
        for device in devices:
            target_devices.append(Device(device))
        return target_devices

    def link_device_to_room(self, room_id, device_id):
        self.collection.update_one({'_id': device_id}, {"$set": {'room_id': room_id}}, upsert=False)
        return self.get_device_by_id(device_id)

    def get_devices_for_room(self, room_id):
        devices = self.collection.find({'room_id': room_id})
        target_devices = []
        for device in devices:
            target_devices.append(Device(device))
        return target_devices

    def get_all_devices(self):
        devices = self.collection.find()
        target_devices = []
        for device in devices:
            target_devices.append(Device(device))
        return target_devices

    def set_power_state(self, device_id, power_state):
        device = self.get_device_by_id(device_id)
        if device.device_type != "light_switch":
            raise Exception("Device is not a switch.")
        device.configure_power_state(power_state)
        self.update_device_reading(device)
        self.collection.update_one({'_id': device_id}, {"$set": {'power_state': power_state}}, upsert=False)

    def set_target_temperature(self, device_id, temp):
        device = self.collection.find_one({'_id': device_id})
        assert (device['device_type'] == "thermostat"), "Device is not a thermostat."
        assert ('locked_min_temperature' not in device['target'] or device['target'][
            'locked_min_temperature'] <= temp), "Chosen temperature is too low."
        assert ('locked_max_temperature' not in device['target'] or device['target'][
            'locked_max_temperature'] >= temp), "Chosen temperature is too high."
        self.collection.update_one({'_id': device_id}, {"$set": {'target': {'target_temperature': temp}}}, upsert=False)
        device = self.get_device_by_id(device_id)
        device.configure_target_temperature(temp)
        self.update_device_reading(device)
        return device

    def change_temperature_scale(self, device_id):
        device = self.collection.find_one({'_id': device_id})
        assert (device['device_type'] == "thermostat"), "Device is not a thermostat."
        if device['temperature_scale'] == "C":
            self.collection.update_one({'_id': device_id}, {"$set": {'temperature_scale': "F"}}, upsert=False)
            new_target_temperature = device['target_temperature'] * 9 / 5 + 32
            new_max_temperature = device['target']['locked_max_temp'] * 9 / 5 + 32
            new_min_temperature = device['target']['locked_min_temp'] * 9 / 5 + 32
            new_last_temperature = device['status']['last_temperature'] * 9 / 5 + 32
        else:
            self.collection.update_one({'_id': device_id}, {"$set": {'temperature_scale': "C"}}, upsert=False)
            new_target_temperature = (device['target']['target_temperature'] - 32) * 5 / 9
            new_max_temperature = (device['target']['locked_max_temp'] - 32) * 5 / 9
            new_min_temperature = (device['target']['locked_min_temp'] - 32) * 5 / 9
            new_last_temperature = (device['target']['last_temperature'] - 32) * 5 / 9
        self.collection.update_one({'_id': device_id},
                                   {"$set": {'target': {'target_temperature': new_target_temperature}}}, upsert=False)
        self.collection.update_one({'_id': device_id}, {"$set": {'target': {'locked_max_temp': new_max_temperature}}},
                                   upsert=False)
        self.collection.update_one({'_id': device_id}, {"$set": {'target': {'locked_min_temp': new_min_temperature}}},
                                   upsert=False)
        self.collection.update_one({'_id': device_id}, {"$set": {'status': {'last_temperature': new_last_temperature}}},
                                   upsert=False)

    def validate_token(self, device_id, token):
        device = self.get_device_by_id(device_id)
        if device is None:
            return False
        else:
            house_id = device.house_id
            return self.repositories.house_repository.validate_token(house_id, token)


class TriggerRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def add_trigger(self, trigger_sensor_id, trigger, actor_id, action):
        pass

    def get_trigger_by_id(self, trigger_id):
        pass


class TokenRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def generate_token(self, user_id):
        unique = False
        token = ""
        while not unique:
            token = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)])
            unique = self.check_token_is_new(token)
        self.add_token(user_id, token)
        return token

    def add_token(self, user_id, token):
        new_token = self.collection.insert_one({'user_id': user_id, 'token': token})
        return new_token.inserted_id

    def invalidate_token(self, token):
        self.collection.delete_one({'token': token})

    def check_token_is_new(self, token):
        result = self.collection.find_one({'token': token})
        if result is not None:
            return False
        else:
            return True

    def check_token_validity(self, token):
        token = self.collection.find({'token': token})
        if token is not None:
            return True
        else:
            return False

    def authenticate_user(self, owner_id, token):
        valid = self.check_token_validity(token)
        if valid:
            token_user_id = self.collection.find_one({'token': token})['user_id']
            user_is_admin = self.repositories.user_repository.get_user_by_id(token_user_id).is_admin
            if token_user_id == owner_id:
                return True
            elif user_is_admin:
                return True
            else:
                return False

    def authenticate_admin(self, token):
        valid = self.check_token_validity(token)
        if valid:
            token_user_id = self.collection.find_one({'token': token})['user_id']
            user_is_admin = self.repositories.user_repository.find_one({'user_id': token_user_id})['is_admin']
            return user_is_admin
        return False

    def get_all_tokens(self):
        tokens = self.collection.find()
        target_tokens = []
        for token in tokens:
            target_tokens.append(Token(token))
        return target_tokens
