import math
import nextcord

from os import environ as env
from datetime import datetime, timedelta
from pytz import timezone as pytimezone
from asyncio import sleep
from typing import Union
from io import StringIO
from html.parser import HTMLParser

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from nextcord.ext import commands, application_checks
from nextcord import (
    Button, 
    ButtonStyle, 
    Colour,
    Embed, 
    Interaction, 
    Member,
    SelectOption, 
    SlashOption, 
    TextChannel, 
    TextInputStyle,
    User, 
    ui, 
    utils, 
    PartialInteractionMessage,
    slash_command)


#GOOGLE VARS
GOOGLE_TOKEN = eval(env['GOOGLE_TOKEN'])
SCOPES = eval(env['SCOPES'])
GOOGLE_CALENDAR_ID = env['GOOGLE_CALENDAR_ID']
UTC = env['UTC']

#DISCORD VARS
CLIENT_ROLE_ID = int(env['CLIENT_ROLE_ID'])
GUILD_ID = int(env['GUILD_ID'])


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

class Calendar():
    def __init__(self) -> None:
        self.creds = self.get_creds()
        self.service = build('calendar', 'v3', credentials=self.creds)

    def get_creds(self) -> Credentials:
        creds = Credentials.from_authorized_user_info(GOOGLE_TOKEN, SCOPES)
        return creds
    
    def get_event(self, eventId):
        return self.service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId).execute()

    def list_events(self, timeMin: Union[datetime, None] = None, timeMax: Union[datetime, None] = None):
        min = timeMin.isoformat() if isinstance(timeMin, datetime) else None
        max = timeMax.isoformat() if isinstance(timeMax, datetime) else None

        result = self.service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=min,
            timeMax=max,
            orderBy="startTime",
            singleEvents=True).execute()

        return result

    def insert_event(self, body: dict):
        return self.service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()
    
    def update_event(self, eventId, body):
        return self.service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId, body=body).execute()  

    def delete_event(self, eventId):
        return self.service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId).execute()

class CalendarEvent():
    def __init__(self, event) -> None:
        if event:
            self.id = event.get('id', None)
            self.summary = event.get('summary', "")
            self.description = event.get('description', "")
            self.start, self.end, self.offset, self.timezone, self.day = self.event_strp(event)
            self.reminders = event.get('reminders', None)
            self.colorId = event.get('colorId', None)
            self.location = event.get('location', "")

    def build_event(self):
        event = {
            'id': self.id, 
            'summary': self.summary, 
            'description': self.description,
            'colorId': self.colorId,
            'location': self.location, 
            'start': {
                'dateTime': self.start.isoformat(), 
                'timeZone': self.timezone
                }, 
            'end': {
                'dateTime': self.end.isoformat(), 
                'timeZone': self.timezone
                }, 
            'reminders': self.reminders, 
            }

        return event

    def check_event(self) -> bool:
        now = datetime.now(pytimezone(UTC))  # 'Z' indicates UTC time
        events = calendar.list_events(now, now + timedelta(days=7)).get('items', [])

        for event in events:
            event = CalendarEvent(event)
            if event.id == self.id and event.summary == self.summary:
                return True
        return False

    def split_disponible(self) -> list:
        start = self.start
        events = []
        while start + timedelta(minutes=30) <= self.end:
            slot = {
                'summary': 'Créneau libre',
                'colorId': 10,
                'start': {
                    'dateTime': (start).isoformat(),
                    'timeZone': self.timezone
                },
                'end': {
                    'dateTime': (start + timedelta(minutes=30)).isoformat(),
                    'timeZone': self.timezone
                }
            }
            start += timedelta(minutes=40)
            events.append(CalendarEvent(calendar.insert_event(slot)))

        calendar.delete_event(self.id)
        return events

    def time_strp(self, time) -> datetime:
        time = datetime.strptime(time, '%Y-%m-%dT%H:%M:%S')
        return time

    def event_strp(self, event) -> tuple[datetime, datetime, str, str, str]:
        start = event['start'].get('dateTime', event['start'].get('date'))
        offset = start[-6:]
        start = start[:-6]
        start = pytimezone(UTC).localize(self.time_strp(start))

        end = event['end'].get('dateTime', event['end'].get('date'))
        end = end[:-6]
        end = pytimezone(UTC).localize(self.time_strp(end))

        timezone: str = event['start'].get('timeZone')
        weekday = self.get_weekday(start.weekday())
        return (start), end, offset, timezone, weekday

    def get_weekday(self, day_number: int) -> str:
        weekdays = {
            0: "Lundi", 
            1: "Mardi", 
            2: "Mercredi",
            3: "Jeudi", 
            4: "Vendredi", 
            5: "Samedi", 
            6: "Dimanche"
            }

        return weekdays[day_number]

    async def cancel_meeting(self, interaction: Union[Interaction, None] = None, event: bool = True):
        if event:
            self.summary = "Créneau libre"
            self.description = ""
            self.location = ""
            self.colorId = 10
            self.reminders = {}

            calendar.update_event(self.id, self.build_event())

        if isinstance(interaction, Interaction):
            embed = Embed(
                title="Rendez-vous annulé!",
                description="Le reservation a été annulé!",
                color=Colour.red()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

calendar = Calendar()
            
class TakeMeetingView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.dropdown: ui.Select

    async def take_meeting(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        now = datetime.now(pytimezone(UTC)) # 'Z' indicates UTC time
        events_result = calendar.list_events(now, now + timedelta(days=7))
        events = events_result.get('items', [])

        slots: dict[str, list[CalendarEvent]] = {}

        for event in events:
            events = CalendarEvent(event)
            if events.summary == "disponible":
                events = events.split_disponible()
                for splited_event in events:
                    splited_event: CalendarEvent
                    if splited_event.start > datetime.now(pytimezone(UTC)):
                        if splited_event.day not in slots:
                            slots[splited_event.day] = []
                        slots[splited_event.day].append(splited_event)
            elif events.summary == "Créneau libre" and events.start > datetime.now(pytimezone(UTC)):
                if events.day not in slots:
                    slots[events.day] = []
                slots[events.day].append(events)

        if slots:
            embed = Embed(
                title="Liste des créneaux",
                color=Colour.blue()
            )
            options: list[SelectOption] = []
            id = 1
            for day in slots:
                day_slots: list[str] = []
                for slot in slots[day]:
                    options.append(SelectOption(label=f"{id}", value=slot.id))
                    day_slots.append(f"{id}. {slot.start.strftime('%H:%M')} - {slot.end.strftime('%H:%M')}")
                    id += 1
                embed.add_field(name=day, value='\n'.join(day_slots), inline=True)

            embed.set_footer(text="Fuseau horaire: UTC+01:00")

            await interaction.followup.send(embed=embed, view=TimeSlotsView(options), ephemeral=True)
        else:
            embed = Embed(
                title="Aucun créneau disponible pour le moment",
                color=Colour.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="Prendre un RDV", style=ButtonStyle.primary, custom_id="meeting_view:primary")
    async def callback(self, button: Union[ui.Button, None], interaction: Interaction) -> None:
        for channel in interaction.channel.category.channels: #type: ignore
            if channel.name.startswith("rdv"):
                author = await MeetingView(CalendarEvent({})).get_meeting_author(channel) #type: ignore
                if author == interaction.user and interaction.guild.get_role(CLIENT_ROLE_ID) not in interaction.user.roles: #type: ignore
                    embed = Embed(
                        title="Vous avez déja pris un rendez-vous",
                        color=Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

        if interaction.guild.get_role(CLIENT_ROLE_ID) in interaction.user.roles: #type: ignore
            embed = Embed(
                title="Engagement", description="En cliquant sur accepter vous vous engager a payer la somme apres le rendez-vous", colour=Colour.blue())
            await interaction.response.send_message(embed=embed, view=AcceptConditionsView(), ephemeral=True)
        else:    
            await self.take_meeting(interaction)


class TimeSlotsView(ui.View):
    def __init__(self, options):
        super().__init__(timeout=60)

        self.add_item(TimeSlotsDropdown(options))

    async def on_timeout(self) -> None:
        return await super().on_timeout()


class TimeSlotsDropdown(ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder="Choisissez un créneau...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: Interaction) -> None:
        event = CalendarEvent(calendar.get_event(self.values[0]))

        if interaction.guild.get_role(CLIENT_ROLE_ID) in interaction.user.roles: #type: ignore
            await interaction.response.defer(ephemeral=True)
        if event.check_event():
            event.summary = "En cours de résérvation..." 
            event.colorId = 5

            event = CalendarEvent(calendar.update_event(event.id, event.build_event()))
            
            if interaction.guild.get_role(CLIENT_ROLE_ID) not in interaction.user.roles: #type: ignore
                await interaction.response.send_modal(Form(event))
                self.view.stop() # type: ignore
            else:

                starting_time = event.start.strftime("%H:%M")
                ending_time = event.end.strftime("%H:%M")

                embed = Embed(title="Voulez vous confirmer?",
                            description=f"Etes vous sur de vouloir reserver le rendez-vous de {event.day} de {starting_time} a {ending_time}?",
                            color=Colour.blue())

                await interaction.followup.send(embed=embed, view=ConfirmMeetingView(event), ephemeral=True)
                self.view.stop() # type: ignore
        else:
            if interaction.guild.get_role(CLIENT_ROLE_ID) not in interaction.user.roles: #type: ignore
                await interaction.response.defer(ephemeral=True)
            embed = Embed(
                title="Le créneau que vous avez choisi n'est plus disponible",
                description="Voulez vous choisir un nouveau?",
                color=Colour.red()
            )
            await interaction.followup.send(embed=embed, view=RetakeMeetingView(event), ephemeral=True)
            self.view.stop() #type: ignore

class Form(ui.Modal):
    def __init__(self, event: CalendarEvent):
        super().__init__("Formulaire", timeout=60*5)

        self.summary = ui.TextInput(
            label="Sujet du rendez-vous",
            placeholder="Définissez un sujet pour le rendez-vous",
            min_length=2,
            max_length=200,
        )
        self.add_item(self.summary)

        self.name = ui.TextInput(
            label="Lien vers la chaine",
            placeholder="Donnez le lien de votre chaine",
            min_length=23,
            max_length=100,
        )
        self.add_item(self.name)

        self.medias = ui.TextInput(
            label="Réseaux sociaux associés a la chaine",
            placeholder="Nom des réseaux separés par des ','",
            required=False,
            min_length=2,
            max_length=300,
        )
        self.add_item(self.medias)

        self.slots = ui.TextInput(
            label="Horaires de streaming",
            placeholder="Les horaires dans lesquels tu es en direct",
            min_length=2,
            max_length=500,
        )
        self.add_item(self.slots)

        self.description = ui.TextInput(
            label="Description de la chaine",
            style=TextInputStyle.paragraph,
            placeholder="Informations sur la chaine, jeux et concepts de la chaine et vos ambitions pour la chaine",
            max_length=1000,
        )
        self.add_item(self.description)

        self.event = event

    async def callback(self, interaction: Interaction) -> None:
        values = [
            strip_tags(self.summary.value).replace("\n", " ").replace("\\n", " "),
            strip_tags(self.name.value).replace("\n", " ").replace("\\n", " "),
            strip_tags(self.medias.value).replace("\n", " ").replace("\\n", " "),
            strip_tags(self.slots.value).replace("\n", " ").replace("\\n", " "),
            strip_tags(self.description.value).replace("\n", " ").replace("\\n", " "),
            str(interaction.user.id) #type: ignore
        ]

        starting_time = self.event.start.strftime("%H:%M")
        ending_time = self.event.end.strftime("%H:%M")

        embed = Embed(
            title="Voulez vous confirmer?",
            description=f"Etes vous sur de vouloir reserver le rendez-vous de {self.event.day} de {starting_time} a {ending_time}?",
            color=Colour.blue())
        
        await interaction.response.send_message(embed=embed, view=ConfirmMeetingView(self.event, values), ephemeral=True)
        self.stop()

    async def on_timeout(self):
        await self.event.cancel_meeting()
        self.stop()

class ConfirmMeetingView(ui.View):
    def __init__(self, event: CalendarEvent, infos: list = []):
        super().__init__(timeout = 60)
        self.value = None
        self.event = event
        self.infos = infos

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @ui.button(label="Confirmer", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:  
        await interaction.response.defer(ephemeral=True)
        description = "\n\n".join([info for info in self.infos if info])

        user = interaction.user
        interaction_channel = interaction.channel 

        self.event.summary = f"Rendez-vous ({interaction.user})"
        self.event.description = description
        self.event.colorId = 7
        self.event.reminders = {
            'useDefault': False,
            'overrides': [
            {'method': 'popup', 'minutes': 10},
        ], 
        }

        channel = None
        content = "@here" #type: ignore
        meetView = MeetingView(self.event)
        message = None
        for rdv_channel in interaction_channel.category.channels: #type: ignore
            if str(rdv_channel.name)[:3] == "rdv":
                author = await MeetingView(CalendarEvent({})).get_meeting_author(rdv_channel)  #type: ignore
                if author == user:
                    channel = rdv_channel
                    meetView = None
                    history = await channel.history(oldest_first=True, limit=1).flatten() #type: ignore
                    message = history[0]  
                    await message.edit(view=MeetingView(self.event))

        for rdv_channel in utils.get(interaction_channel.guild.categories, name="Archives").channels: #type: ignore
            if str(rdv_channel.name)[:3] == "rdv":
                author = await MeetingView(CalendarEvent({})).get_meeting_author(rdv_channel) #type: ignore
                if author == user:
                    channel = rdv_channel
                    meetView = None
                    await channel.edit(category=interaction_channel.category, sync_permissions=True) #type: ignore
                    await channel.set_permissions(author, view_channel=True) #type: ignore
                    await channel.purge(limit=1)  #type: ignore
                    history = await channel.history(oldest_first=True, limit=1).flatten()  #type: ignore
                    message = history[0]
                    await message.edit(view=MeetingView(self.event)) 

        if not channel:
            channel = await interaction_channel.guild.create_text_channel(name=f"rdv-{str(user).replace(' ', '')}", category=interaction_channel.category) #type: ignore
            #type: ignore
            await channel.set_permissions(user, view_channel=True) #type: ignore
            

        self.event.location = channel.id
        calendar.update_event(self.event.id, self.event.build_event())

        embed = Embed(
                title=f"Rendez-vous de {user}",
                description=f"{self.event.day} de {self.event.start.strftime('%H:%M')} a {self.event.end.strftime('%H:%M')}",
                colour=Colour.blue(),
            )
        embed.set_footer()

        
        
        msg = await channel.send(content, view=meetView, embed=embed) #type: ignore
        await msg.pin()
        embed = Embed(
                title="Rendez-vous pris!",
                description="Le rendez-vous a bien été reservé!",
                color=Colour.green()
            )

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.value = True
        self.stop()

        if not message:
            message = msg

        await MeetingView(self.event).schedule_alert(interaction_channel.guild, user, message) #type: ignore
            

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        await self.event.cancel_meeting(interaction)
        self.value = False
        self.stop()

    async def on_timeout(self) -> None:
        if not self.value:
            await self.event.cancel_meeting()
        self.stop()


class MeetingView(ui.View):
    def __init__(self, event: CalendarEvent):
        super().__init__(timeout=None)
        self.event = event

    async def schedule_alert(self, guild, user, message: PartialInteractionMessage) -> None: 
        await message.edit(view=self)
        wait = int((self.event.start-(datetime.now(pytimezone(UTC)))).total_seconds())
        if wait > 600:
            await sleep(wait - 600)
        if self.event.location:
            rdv_channel = guild.get_channel(int(self.event.location))

            if str(rdv_channel.category) == "Rendez-vous":  
                if self.event.check_event():
                    wait = int(
                        (self.event.start-(datetime.now(pytimezone(UTC)))).total_seconds())
                    embed = Embed(
                            title=f"Le rendez-vous est dans {int(math.ceil(wait / 60))} minutes",
                            color=Colour.blue()
                        )

                    await rdv_channel.send("@here", embed=embed) 
                    await sleep(wait)
                else:   
                    embed = Embed(
                        title="Le rendez-vous a été annulé",
                        color=Colour.red()
                    )
                    await rdv_channel.send("@here", embed=embed)  
            else:
                await self.event.cancel_meeting()
                return
        else:
            await self.event.cancel_meeting()
            return
        

        if self.event.location:
            rdv_channel = guild.get_channel(int(self.event.location))

            if str(rdv_channel.category) == "Rendez-vous":  
                if self.event.check_event():
                    embed = Embed(
                        title="Le rendez-vous a commencé",
                        color=Colour.green()
                    )

                    await rdv_channel.send("@here", embed=embed) 
                    await user.add_roles(guild.get_role(CLIENT_ROLE_ID))  
                    wait = int((self.event.end-(datetime.now(pytimezone(UTC)))).total_seconds())
                    await sleep(wait)
                    embed = Embed(
                        title="Le rendez-vous est fini",
                        color=Colour.red()
                    )

                    await rdv_channel.send("@here", embed=embed) 
                    for button in self.children:
                        button.disabled = False  #type: ignore
                    await message.edit(view=self)  
                else:
                    embed = Embed(
                        title="Le rendez-vous a été annulé",
                        color=Colour.red()
                    )

                    await rdv_channel.send("@here", embed=embed) 
            else:
                await self.event.cancel_meeting()
                return
        else:
            await self.event.cancel_meeting()
            return

    async def get_meeting_author(self, channel: TextChannel) -> Union[Member, User]:
        history = await channel.history(oldest_first=True, limit=1).flatten()
        user: Union[Member, User] = history[0].mentions[0]
        return user

    async def close_meeting(self, interaction: Interaction) -> None:
        embed_reply = Embed(
            title="Ce salon a été fermé",
            colour=Colour.dark_theme(),
        )
        channel = interaction.channel
        channel_author = await self.get_meeting_author(channel)  #type: ignore
        closed_by = interaction.user

        # Send the closing message to the help thread
        await channel.send(embed=embed_reply) #type: ignore
        #type: ignore
        await channel.set_permissions(channel_author, read_messages=False) #type: ignore

        # Send log
        embed_log = Embed(
            title=":x: Rendez-vous férmé",
            description=(
                f"{channel.mention}\n\nRendez vous crée par {channel_author.mention} a été férmé par {closed_by.mention}.\n\n" #type: ignore
                f"Createur: `{channel_author} ({channel_author.id})`\n"
                f"Férmé par: `{closed_by} ({closed_by.id})`"  #type: ignore
            ),
            colour=0xDD2E44,  # Red
        )

        await channel.edit(category=utils.get(channel.guild.categories, name="Archives"), sync_permissions=True) #type: ignore
        await utils.get(interaction.guild.channels, name="logs").send(embed=embed_log) #type: ignore
        if self.event:
            if datetime.now(pytimezone(UTC)) < self.event.start:
                await self.event.cancel_meeting()


    @ui.button(label="Reprendre un RDV", style=ButtonStyle.primary, custom_id=f"take_other_meet", disabled=True)
    async def take_other_meeting(self, button: Button, interaction: Interaction) -> None:
        embed = Embed(title="Engagement", description="En cliquant sur accepter vous vous engager a payer apres le rendez-vous", colour=Colour.blue())
        await interaction.response.send_message(embed=embed, view=AcceptConditionsView(), ephemeral=True)
    
    @ui.button(label="Fermer", style=ButtonStyle.red, custom_id=f"meet_close_button")
    async def close_meeting_button(self, button: Button, interaction: Interaction) -> None:
        for children in self.children:
            children.disabled = True  #type: ignore
        await interaction.response.edit_message(view=self)
        await self.close_meeting(interaction)


class AcceptConditionsView(ui.View):
    def __init__(self):
        super().__init__(timeout = 60*2)
        self.value = None


    @ui.button(label="Accepter", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:
        await TakeMeetingView().take_meeting(interaction)
        self.value = True
        self.stop()


    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        self.value = False
        self.stop()


class RetakeMeetingView(ui.View):
    def __init__(self, event):
        super().__init__(timeout = None)
        self.value = None
        self.event = event

    @ui.button(label="Confirmer", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:
        await TakeMeetingView().take_meeting(interaction)
        self.value = True
        self.stop()

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        await self.event.cancel_meeting(interaction, False)
        self.value = False
        self.stop()


class Meetings(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.client.loop.create_task(self.create_views())
        self.client.loop.create_task(self.get_alerts())
        

    async def create_views(self):
        self.client.add_view(TakeMeetingView())
        self.client.add_view(MeetingView(CalendarEvent({})))
        

    async def get_alerts(self):
        await self.client.wait_until_ready()
        events = calendar.list_events(timeMin=(datetime.now(pytimezone(UTC)) - timedelta(minutes=30))).get('items', [])

        for event in events:
            event = CalendarEvent(event)
            if event.summary.startswith("Rendez-vous") and datetime.now(pytimezone(UTC)) < event.end:
                description = event.description.split("\n\n")
                channel = self.client.get_channel(int(event.location))
                history = await channel.history(oldest_first=True, limit=1).flatten() #type: ignore
                message = history[0]
                guild = self.client.get_guild(GUILD_ID)
                await MeetingView(event).schedule_alert(guild, guild.get_member(int(description[len(description)-1])), message)  #type: ignore  


    @application_checks.has_permissions(manage_messages=True)
    @slash_command(name="clear", description="Pour purger le salon")
    async def clear(
            self,
            interaction: Interaction,
            channel: TextChannel = SlashOption(name="channel", description="Choisissez un salon", required=False),
            limit: int = SlashOption(name="limit", description="Definissez une limite de messages", required=False)) -> None:

        if not channel:
            channel = interaction.channel #type: ignore
        
        await channel.purge(limit=int(limit) if limit else None)
        
        embed = Embed(title="Le salon a été purgé", color=nextcord.Colour.green())

        await interaction.response.send_message(embed=embed, ephemeral=True)


    @application_checks.is_owner()
    @slash_command(name="prepare")
    async def prepare(self, interaction: Interaction):
        await interaction.channel.purge() #type: ignore
        embed = Embed(title="Prise de Rendez-Vous", description="Pour prendre un rendez-vous", color=nextcord.Colour.blue())
        embed.set_footer(text="Vous pouvez enlever les messages en apppuyant sur \"rejeter le message\"")
        await interaction.response.send_message(embed=embed, view=TakeMeetingView())


    @application_checks.is_owner()
    @slash_command(name="clear_calendar")
    async def clear_calendar(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        events = calendar.list_events().get('items', [])
        for event in events:
            event = CalendarEvent(event)
            calendar.delete_event(event.id)

        await interaction.followup.send(embed=Embed(title="L'agenda a été purgé", color=nextcord.Colour.green()))

    @application_checks.is_owner()
    @slash_command(name="clear_archives")
    async def clear_archives(self, interaction: Interaction):
        for archived_meeting in utils.get(interaction.guild.categories, name="Archives").channels: #type: ignore
            await archived_meeting.delete()

        await interaction.response.send_message(embed=Embed(title="Les archives ont été purgées", color=nextcord.Colour.green()), ephemeral=True)

def setup(client):
    client.add_cog(Meetings(client))
