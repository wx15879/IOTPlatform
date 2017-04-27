import datetime
import logging
import random
import string

import bcrypt

from model import House, Room, User, Device, Thermostat, MotionSensor, LightSwitch, OpenSensor, Trigger, Theme, Token


class RepositoryException(Exception):
    def __init__(self, message, error_data):
        Exception.__init__(self, message)
        self.error_data = error_data


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
        self.theme_repository = ThemeRepository(db.themes, self)
        self.token_repository = TokenRepository(db.token, self)


class UserRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def update_user_account(self, user_id, name, password):
        user = self.get_user_by_id(user_id)
        if user is None:
            return False
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        self.collection.update_one({'_id': user_id}, {"$set": {'name': name, 'password_hash': password_hash}})

        return True

    def add_user(self, name, password_hash, email_address, is_admin):
        existing_user = self.get_user_by_email(email_address)
        if existing_user is not None:
            raise Exception("There is already an account with this email.")
        user = self.collection.insert_one({'name': name, 'password_hash': password_hash,
                                           'email_address': email_address, 'is_admin': is_admin,
                                           'faulty': False})
        return user.inserted_id

    def register_new_user(self, email_address, password, name, is_admin):
        user = self.get_user_by_email(email_address)
        if user is not None:
            raise RepositoryException("Email address already registered",
                                      {'code': 409, 'message': 'Email address is already registered'})
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        return self.add_user(name, hashed_password, email_address, is_admin)

    def check_password(self, email_address, password):
        login_user = self.get_user_by_email(email_address)
        if login_user is not None:
            logging.debug('password: {}'.format(password.encode('utf-8')))
            logging.debug('hash:     {}'.format(login_user.password_hash))
            if bcrypt.checkpw(password.encode('utf-8'), login_user.password_hash.encode('utf-8')):
                return login_user
            else:
                raise RepositoryException("Password is incorrect", {'code': 406, 'message': 'Password is incorrect'})
        else:
            raise RepositoryException("Username not found", {'code': 404, 'message': 'Username not found'})

    def remove_user(self, user_id):
        user = self.get_user_by_id(user_id)
        self.collection.delete_one({'_id': user_id})
        return user

    def get_user_by_id(self, user_id):
        user = self.collection.find_one({'_id': user_id})
        if user is None:
            return None
        target_user = User(user)
        return target_user

    def get_user_by_email(self, email_address):
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

    def get_faulty_devices_for_user(self, user_id):
        faulty_devices = self.repositories.device_repository.get_faulty_devices()
        house_id = self.collection.get_houses_for_user(user_id)[0].house_id
        target_devices = []
        fault_check = False
        for device in faulty_devices:
            if device.house_id == house_id:
                fault_check = True
                target_devices.append(Device(device))
        self.collection.update_one({'_id': user_id}, {"$set": {'faulty': fault_check}}, upsert=False)
        return target_devices

    def validate_token(self, user_id, token):
        user = self.get_user_by_id(user_id)
        if user is None:
            return False
        else:
            return self.repositories.token_repository.authenticate_user(user_id, token)


class HouseRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def add_house(self, user_id, name, location):
        user_houses = self.get_houses_for_user(user_id)
        for house in user_houses:
            other_name = house.name
            if name == other_name:
                raise Exception("There is already a house with this name.")
        house = self.collection.insert_one({'user_id': user_id, 'name': name, 'location': location})
        return house.inserted_id

    def update_house(self, house_id, name, location):
        house = self.get_house_by_id(house_id)
        if house is None:
            return False
        self.collection.update_one({'_id': house_id}, {"$set": {'name': name, 'location': location}})
        return True

    def remove_house(self, house_id):
        house = self.get_house_by_id(house_id)
        self.collection.delete_one({'_id': house_id})
        return house

    def get_house_by_id(self, house_id):
        house = self.collection.find_one({'_id': house_id})
        target_house = House(house)
        return target_house

    def get_house_by_location(self, location):
        house = self.collection.find_one({'location': location})
        return house

    def get_houses_for_user(self, user_id):
        houses = self.collection.find({'user_id': user_id})
        target_houses = []
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
        room = self.get_room_by_id(room_id)
        self.collection.delete_one({'_id': room_id})
        devices = self.repositories.device_repository.get_devices_for_room(room_id)
        for device in devices:
            self.repositories.device_repository.unlink_device_from_room(device.device_id)
        return room

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
        self.collection.update_one({'_id': device.get_device_id()},
                                   {"$set": {'status.last_read': reading}})

    def update_all_device_readings(self):
        all_device_ids = [x['_id'] for x in self.collection.find({}, {})]
        for device_id in all_device_ids:
            device = self.get_device_by_id(device_id)
            self.update_device_reading(device)

    def add_device(self, house_id, room_id, name, device_type, target, status, configuration, vendor):
        house_devices = self.get_devices_for_house(house_id)
        for device in house_devices:
            other_name = device.name
            if name == other_name:
                raise Exception("There is already a device with this name.")
        if vendor == "OWN" and "url" not in configuration:
            raise Exception("Not all required info is in the configuration.")
        elif vendor == "energenie" and \
                ("username" not in configuration
                 or "password" not in configuration
                 or "device_id" not in configuration):
            raise Exception("Not all required info is in the configuration.")
        device = self.collection.insert_one({'house_id': house_id, 'room_id': room_id,
                                             'name': name, 'device_type': device_type, 'locking_theme_id': None,
                                             'target': target, 'status': status,
                                             'configuration': configuration,
                                             'vendor': vendor})
        device_id = device.inserted_id
        self.collection.update_one({'_id': device_id}, {"$set": {'status.last_read': 0}})
        self.set_device_type(device_id)
        device = self.get_device_by_id(device_id=device_id)
        self.update_device_reading(device)
        return device_id

    def set_device_type(self, device_id):
        device = self.collection.find_one({'_id': device_id})
        if device['device_type'] == "thermostat":
            self.collection.update_one({'_id': device_id}, {"$set": {'target.locked_max_temperature': 50}})
            self.collection.update_one({'_id': device_id}, {"$set": {'target.locked_min_temperature': 0}})
            self.collection.update_one({'_id': device_id}, {"$set": {'temperature_scale': "C"}})
            self.collection.update_one({'_id': device_id}, {"$set": {'target.target_temperature': 25}})
            self.collection.update_one({'_id': device_id}, {"$set": {'status.last_temperature': 0}})
        elif device['device_type'] == "motion_sensor":
            self.collection.update_one({'_id': device_id}, {"$set": {'sensor_data': 0}})
        elif device['device_type'] == "light_switch":
            self.collection.update_one({'_id': device_id}, {"$set": {'status.power_state': 0}})
        elif device['device_type'] == "open_sensor":
            self.collection.update_one({'_id': device_id}, {"$set": {'sensor_data': 0}})

    def remove_device(self, device_id):
        device = self.get_device_by_id(device_id)
        self.collection.delete_one({'_id': device_id})
        return device

    def unlink_device_from_room(self, device_id):
        self.collection.update_one({'device_id': device_id}, {"$set": {'room_id': None}}, upsert=False)

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
        if power_state not in [0, 1]:
            raise Exception("Power_state is not of the correct format")
        if device.locking_theme_id is None:
            device.configure_power_state(power_state)
            self.update_device_reading(device)
            self.collection.update_one({'_id': device_id}, {"$set": {'status.power_state': power_state}}, upsert=False)

    def set_target_temperature(self, device_id, temp):
        device = self.collection.find_one({'_id': device_id})
        assert (device['device_type'] == "thermostat"), "Device is not a thermostat."
        assert ('locked_min_temperature' not in device['target'] or device['target'][
            'locked_min_temperature'] <= temp), "Chosen temperature is too low."
        assert ('locked_max_temperature' not in device['target'] or device['target'][
            'locked_max_temperature'] >= temp), "Chosen temperature is too high."
        if device['locking_theme_id'] is None:
            self.collection.update_one({'_id': device_id}, {"$set": {'target.target_temperature': temp}}, upsert=False)
            device = self.get_device_by_id(device_id)
            device.configure_target_temperature(temp)
            self.update_device_reading(device)
        return device

    def set_locking_theme_id(self, device_id, locking_theme_id):
        device = self.get_device_by_id(device_id)
        device.locking_theme_id = locking_theme_id
        self.collection.update_one({'_id': device_id}, {"$set": {'locking_theme_id': locking_theme_id}})
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
                                   {"$set": {'target.target_temperature': new_target_temperature}}, upsert=False)
        self.collection.update_one({'_id': device_id}, {"$set": {'target.locked_max_temp': new_max_temperature}},
                                   upsert=False)
        self.collection.update_one({'_id': device_id}, {"$set": {'target.locked_min_temp': new_min_temperature}},
                                   upsert=False)
        self.collection.update_one({'_id': device_id}, {"$set": {'status.last_temperature': new_last_temperature}},
                                   upsert=False)

    def get_energy_consumption(self, device_id):
        device = self.get_device_by_id(device_id)
        consumption = device.get_energy_readings()
        logging.debug("Got energy consumption: {}".format(consumption))
        consumption_array = consumption["data"]["data"]
        consumption_array = list(reversed(consumption_array))
        for i in range(0, len(consumption_array)):
            consumption_array[i][0] = datetime.datetime.fromtimestamp(consumption_array[i][0]).date()
        return consumption_array

    def get_overall_consumption(self):
        devices = self.get_all_devices()
        overall_consumption = []
        for device in devices:
            device_consumption = self.get_energy_consumption(device.device_id)
            if device_consumption is not None:
                if len(overall_consumption) == 0:
                    overall_consumption = device_consumption
                else:
                    for i in range(len(overall_consumption)):
                        j = 0
                        while overall_consumption[i][0] != device_consumption[j][0]:
                            if j < len(device_consumption):
                                j += 1
                            else:
                                break
                        if j < len(device_consumption):
                            overall_consumption[i][1] = overall_consumption[i][1] + device_consumption[j][1]
        return overall_consumption

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

    def add_trigger(self, sensor_id, event, event_params, actor_id, action, action_params, user_id):
        new_trigger = self.collection.insert_one({'sensor_id': sensor_id, 'event': event, 'event_params': event_params,
                                                  'actor_id': actor_id, 'action': action,
                                                  'action_params': action_params,
                                                  'user_id': user_id, 'reading': None})
        return new_trigger.inserted_id

    def remove_trigger(self, trigger_id):
        trigger = self.get_trigger_by_id(trigger_id)
        self.collection.delete_one({'_id': trigger_id})
        return trigger

    def get_trigger_by_id(self, trigger_id):
        trigger = self.collection.find_one({'_id': trigger_id})
        if trigger is None:
            return None
        target_trigger = Trigger(trigger)
        return target_trigger

    def get_triggers_for_device(self, device_id):
        triggers = self.collection.find({'actor_id': device_id})
        target_triggers = []
        for trigger in triggers:
            target_triggers.append(Trigger(trigger))
        return target_triggers

    def get_actions_for_device(self, device_id):
        triggers = self.collection.find({'sensor_id': device_id})
        target_triggers = []
        for trigger in triggers:
            target_triggers.append(Trigger(trigger))
        return target_triggers

    def edit_trigger(self, trigger_id, event, event_params, action, action_params):
        self.collection.update_one({'_id': trigger_id},
                                   {"$set": {"event": event, "event_params": event_params,
                                             "action": action, "action_params": action_params}})
        return self.get_trigger_by_id(trigger_id)

    def get_triggers_for_user(self, user_id):
        triggers = self.collection.find({'user_id': user_id})
        target_triggers = []
        for trigger in triggers:
            target_triggers.append(Trigger(trigger))
        return target_triggers

    def get_all_triggers(self):
        triggers = self.collection.find()
        target_triggers = []
        for trigger in triggers:
            target_triggers.append(Trigger(trigger))
        return target_triggers

    def check_all_triggers(self):
        triggers = self.get_all_triggers()
        for trigger in triggers:
            triggered = False
            if trigger.event == "motion_detected_start" or trigger.event == "motion_detected_stop":
                pass
            elif trigger.event == "temperature_gets_higher_than" or trigger.event == "temperature_gets_lower_than":
                pass
            if triggered:
                if trigger.action == "set_target_temperature":
                    pass
                elif trigger.action == "set_light_switch":
                    pass

    def update_trigger_reading(self, trigger_id, reading):
        self.collection.update_one({'_id': trigger_id}, {"$set": {'reading': reading}})

    def validate_token(self, trigger_id, token):
        trigger = self.get_trigger_by_id(trigger_id)
        if trigger is None:
            return False
        else:
            user_id = trigger.user_id
            return self.repositories.token_repository.authenticate_user(user_id, token)


class ThemeRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def add_theme(self, user_id, name, settings, active):
        new_theme = self.collection.insert_one(
            {'user_id': user_id, 'name': name, 'settings': settings, 'active': active})
        return new_theme.inserted_id

    def remove_theme(self, theme_id):
        theme = self.get_theme_by_id(theme_id)
        self.collection.delete_one({'_id': theme_id})
        return theme

    def remove_device_from_theme(self, theme_id, device_id):
        theme = self.get_theme_by_id(theme_id)
        for dev in theme.settings:
            if dev['device_id'] == device_id:
                theme.settings.remove(dev)
        updated_settings = theme.settings
        self.collection.update_one({'_id': theme_id}, {"$set": {'settings': updated_settings}})
        updated_theme = self.get_theme_by_id(theme_id)
        return updated_theme

    def get_theme_by_id(self, theme_id):
        theme = self.collection.find_one({'_id': theme_id})
        if theme is None:
            return None
        target_theme = Theme(theme)
        return target_theme

    def get_themes_for_user(self, user_id):
        user = self.collection.find({'user_id': user_id})
        target_themes = []
        for theme in user:
            target_themes.append(Theme(theme))
        return target_themes

    def get_all_themes(self):
        themes = self.collection.find()
        target_themes = []
        for theme in themes:
            target_themes.append(Theme(theme))
        return target_themes

    def edit_theme(self, theme_id, settings):
        self.collection.update_one({'_id': theme_id}, {"$set": {"settings": settings}})
        return self.get_theme_by_id(theme_id)

    # The next 2 functions are very similar, but I didn't combine them for the sake of clarity.
    def edit_device_settings(self, theme_id, device_id, setting):
        settings = self.get_theme_by_id(theme_id).settings
        new_settings = settings.replace(settings['setting'], setting)
        self.collection.update_one({'_id': theme_id}, {"$set": {'settings': new_settings}})
        updated_theme = self.get_theme_by_id(theme_id)
        return updated_theme

    def add_device_to_theme(self, theme_id, device_id, setting):
        theme = self.get_theme_by_id(theme_id)
        settings = theme.settings
        new_settings = settings.append({'device_id': device_id, 'setting': setting})
        self.collection.update_one({'_id': theme_id}, {"$set": {'settings': new_settings}})
        updated_theme = self.get_theme_by_id(theme_id)
        return updated_theme

    def change_theme_state(self, theme_id, state):
        theme = self.get_theme_by_id(theme_id)
        settings = theme.settings
        ids = [dev['device_id'] for dev in settings]
        if state is False:
            theme.active = False
            for device_id in ids:
                DeviceRepository.set_locking_theme_id(device_id, None)
            self.collection.update_one({'_id': theme_id}, {"$set": {'active': False}})
        elif state is True:
            theme.active = True
            for dev in settings:
                device_setting = dev['setting']
                if 'target_temp' in device_setting:
                    target_temp = device_setting['target_temperature']
                    self.repositories.device_repository.set_target_temperature(dev['device_id'], target_temp)
                elif 'power_state' in device_setting:
                    power_state = device_setting['power_state']
                    self.repositories.device_repository.set_power_state(dev['device_id'], power_state)
                self.repositories.device_repository.set_locking_theme_id(dev['device_id'], theme_id)
            self.collection.update_one({'_id': theme_id}, {"$set": {'active': True}})
        else:
            raise Exception("Theme active state is not in the correct format")
        updated_theme = self.get_theme_by_id(theme_id)
        return updated_theme

    def validate_token(self, theme_id, token):
        theme = self.get_theme_by_id(theme_id)
        if theme is None:
            return False
        else:
            user_id = theme.user_id
            return self.repositories.token_repository.authenticate_user(user_id, token)


class TokenRepository(Repository):
    def __init__(self, mongo_collection, repository_collection):
        Repository.__init__(self, mongo_collection, repository_collection)

    def find_by_token(self, token):
        return self.collection.find_one({'token': token})

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

    def get_token_info(self, token):
        token = self.collection.find_one({'token': token})
        if token is None:
            return None
        target_token = Token(token)
        return target_token

    def check_token_is_new(self, token):
        result = self.find_by_token(token)
        if result is not None:
            return False
        else:
            return True

    def check_token_validity(self, token):
        token = self.find_by_token(token)
        if token is not None:
            return True
        else:
            return False

    def authenticate_user(self, owner_id, token):
        valid = self.check_token_validity(token)
        if valid:
            token_user_id = self.find_by_token(token)['user_id']
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
            token_user_id = self.find_by_token(token)['user_id']
            user_is_admin = self.repositories.user_repository.get_user_by_id(token_user_id).is_admin
            return user_is_admin
        return False

    def get_all_tokens(self):
        tokens = self.collection.find()
        target_tokens = []
        for token in tokens:
            target_tokens.append(Token(token))
        return target_tokens
