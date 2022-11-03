from asyncio import sleep
from datetime import datetime, timedelta
import math
from os import environ as env
from os import path
from typing import Union

import nextcord
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from nextcord import (Button, ButtonStyle, ClientUser, Colour,
                      Embed, Interaction, Member, PermissionOverwrite, Role,
                      SelectOption, SlashOption, TextChannel, TextInputStyle,
                      User, slash_command, ui, utils, PartialInteractionMessage)

from nextcord.ext import commands

GOOGLE_CREDITENTIALS = eval(env['GOOGLE_CREDITENTIALS'])
GOOGLE_TOKEN = eval(env['GOOGLE_TOKEN'])
SCOPES = [env['SCOPES'],]
GOOGLE_CALENDAR_ID = env['GOOGLE_CALENDAR_ID']

CLIENT_ROLE = int(env['CLIENT_ROLE'])
MODERATION_ROLE = int(env['MODERATION_ROLE'])

class Calendar():
    def __init__(self) -> None:
        self.creds = self.get_creds()
        self.service = build('calendar', 'v3', credentials=self.creds)

    def get_creds(self) -> Credentials:
        creds = Credentials.from_authorized_user_info(GOOGLE_TOKEN, SCOPES)
        
        return creds
    
    def get(self, eventId):
        return self.service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId).execute()

    def list(self, timeMin: Union[datetime, None] = None, timeMax: Union[datetime, None] = None):
        min = None
        if isinstance(timeMin, datetime):
            min = timeMin.isoformat() + 'Z'

        max = None
        if isinstance(timeMax, datetime):
            max = timeMax.isoformat() + 'Z'

        result = self.service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=min,
            timeMax=max,
            singleEvents=True,
            orderBy='startTime').execute()
        return result

    def insert(self, body: dict):
        return self.service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()
    
    def update(self, eventId, body):
        return self.service.events().update(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId, body=body).execute()  

    def delete(self, eventId):
        return self.service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=eventId).execute()

class CalendarEvent():
    def __init__(self, event) -> None:
        self.kind = event.get('kind', None)
        self.etag = event.get('etag', None)
        self.id = event.get('id', None)
        self.status = event.get('status', None)
        self.htmlLink = event.get('htmlLink', None)
        self.created = event.get('created', None)
        self.updated = event.get('updated', None)
        self.summary = event.get('summary', "")
        self.description = event.get('description', "")
        self.creator = event.get('creator', None)
        self.organizer = event.get('organizer', None)
        self.start, self.end, self.offset, self.timezone = self.event_strp(event)
        self.day = self.get_weekday(self.start.weekday())
        self.iCalUID = event.get('iCalUID', None)
        self.sequence = event.get('sequence', None)
        self.reminders = event.get('reminders', None)
        self.eventType = event.get('eventType', None)
        self.colorId = event.get('colorId', None)
        self.location = event.get('location', "")

        if self.summary == "disponible":
            self.split_dispo()

    def build(self):
        event = {
            'kind': self.kind, 
            'etag': self.etag, 
            'id': self.id, 
            'status': self.status, 
            'htmlLink': self.htmlLink, 
            'created': self.created, 
            'updated': self.updated, 
            'summary': self.summary, 
            'description': self.description,
            'location': self.location, 
            'creator': self.creator,
            'organizer': self.organizer, 
            'start': {
                'dateTime': self.start.isoformat()+self.offset, 
                'timeZone': self.timezone
                }, 
            'end': {
                'dateTime': self.end.isoformat()+self.offset, 
                'timeZone': self.timezone
                }, 
            'iCalUID': self.iCalUID, 
            'sequence': self.sequence, 
            'reminders': self.reminders, 
            'eventType': self.eventType
            }

        return event

    def check_event(self) -> bool:
        now = datetime.utcnow()  # 'Z' indicates UTC time
        events_result = calendar.list(now, now + timedelta(days=7))
        events = events_result.get('items', [])

        for event in events:
            event = CalendarEvent(event)
            if event.id == self.id and event.summary == self.summary:
                return True
        return False

    def split_dispo(self) -> None:
        start = self.start
        while start + timedelta(minutes=30) <= self.end:
            slot = {
                'summary': 'Créneau libre',
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
            calendar.insert(slot)

        calendar.delete(self.id)

    def time_strp(self, time) -> datetime:
        time = datetime.strptime(time, '%Y-%m-%dT%H:%M:%S')
        return time

    def event_strp(self, event) -> tuple[datetime, datetime, str, str]:
        start = event['start'].get('dateTime', event['start'].get('date'))
        offset = start[-6:]
        start = start[:-6]
        start = self.time_strp(start)

        end = event['end'].get('dateTime', event['end'].get('date'))
        end = end[:-6]
        end = self.time_strp(end)

        timezone: str = event['start'].get('timeZone')
        return start, end, offset, timezone

    def get_weekday(self, number: int) -> str:
        weekdays = {
            0: "Lundi", 
            1: "Mardi", 
            2: "Mercredi",
            3: "Jeudi", 
            4: "Vendredi", 
            5: "Samedi", 
            6: "Dimanche"
            }

        return weekdays[number]

    async def cancel_rdv(self, interaction: Union[Interaction, None] = None, event: bool = True):
        if event:
            self.summary = "Créneau libre"
            self.description = ""
            self.location = ""
            self.reminders = {}

            calendar.update(self.id, self.build())

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
        self.message = None

    async def take_meeting(self, interaction: Interaction):
        now = datetime.utcnow()  # 'Z' indicates UTC time
        events_result = calendar.list(now, now + timedelta(days=7))
        events = events_result.get('items', [])
        for event in events:
            event = CalendarEvent(event)

        events_result = calendar.list(now, now + timedelta(days=7))
        events = events_result.get('items', [])

        slots: dict[str, list[CalendarEvent]] = {}

        for event in events:
            event = CalendarEvent(event)
            if event.summary == "Créneau libre":
                if event.day not in slots:
                    slots[event.day] = []
                slots[event.day].append(event)

        if slots:
            embed = Embed(
                title="Liste des créneaux",
                color=Colour.blue()
            )
            options: list[SelectOption] = []
            id = 1
            for day in slots:
                crens: list[str] = []
                for slot in slots[day]:
                    options.append(SelectOption(label=f"{id}", value=slot.id))
                    crens.append(
                        f"{id}. {slot.start.strftime('%H:%M')} - {slot.end.strftime('%H:%M')}")
                    id += 1
                embed.add_field(name=day, value='\n'.join(crens), inline=True)

            timeSlotsView = TimeSlotsView(options)

            self.message = await interaction.response.send_message(embed=embed, view=timeSlotsView, ephemeral=True)
        else:
            embed = Embed(
                title="Aucun créneau disponible pour le moment",
                color=Colour.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Prendre un RDV", style=ButtonStyle.primary, custom_id="meeting_view:primary")
    async def callback(self, button: Union[ui.Button, None], interaction: Interaction) -> None:
        for channel in interaction.channel.category.channels:  
            if str(channel.name)[:3] == "rdv":
                author = await MeetingView().get_thread_author(channel)  
                if author == interaction.user and interaction.guild.get_role(CLIENT_ROLE) not in interaction.user.roles: 
                    embed = Embed(
                        title="Vous avez déja pris un rendez-vous",
                        color=Colour.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

        if interaction.guild.get_role(CLIENT_ROLE) in interaction.user.roles: 
            embed = Embed(
                title="Engagement", description="En cliquant sur accepter vous vous engager a payer apres le rendez-vous", colour=Colour.blue())
            await interaction.response.send_message(embed=embed, view=AcceptConditionsView(), ephemeral=True)
        else:    
            await self.take_meeting(interaction)


class TimeSlotsView(ui.View):
    def __init__(self, options):
        super().__init__()

        # Adds the dropdown to our view object.
        self.add_item(TimeSlotsDropdown(options))


class TimeSlotsDropdown(ui.Select):
    def __init__(self, options):
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(
            placeholder="Choisissez un créneau...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: Interaction) -> None:
        event = calendar.get(self.values[0])
        event = CalendarEvent(event)
        if event.check_event():
            event.summary = "En cours de résérvation..." 
            event.colorId = "5"

            event = calendar.update(event.id, event.build())
            event = CalendarEvent(event)
            
            if interaction.guild.get_role(CLIENT_ROLE) not in interaction.user.roles:  
                form = Form(event)
                await interaction.response.send_modal(form)
            else:
                starting_time = event.start.strftime("%H:%M")
                ending_time = event.end.strftime("%H:%M")

                embed = Embed(title="Voulez vous confirmer?",
                            description=f"Etes vous sur de vouloir reserver le rendez-vous de {event.day} de {starting_time} a {ending_time}?",
                            color=Colour.blue())

                confirmView = ConfirmMeetingView(event)
                await interaction.response.send_message(embed=embed, view=confirmView, ephemeral=True)
        else:
            embed = Embed(
                title="Le créneau que vous avez choisi n'est plus disponible",
                description="Voulez vous choisir un nouveau?",
                color=Colour.red()
            )
            retakeMeetingView = RetakeMeetingView(event)
            await interaction.response.send_message(embed=embed, view=retakeMeetingView, ephemeral=True)
            

class Form(ui.Modal):
    def __init__(self, event: CalendarEvent):
        super().__init__("Formulaire", timeout=15)

        self.summary = ui.TextInput(
            label="Sujet du rendez-vous",
            placeholder="Définissez un sujet pour le rendez-vous",
            min_length=2,
            max_length=200,
        )
        self.add_item(self.summary)

        self.name = ui.TextInput(
            label="Chaine",
            placeholder="Nom de la chaine, et lien vers la chaine entre parentheses",
            min_length=15,
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
        values = {
            "sujet": self.summary.value,
            "nom": self.name.value,
            "medias": self.medias.value,
            "horaires": self.slots.value,
            "description": self.description.value,
        }

        starting_time = self.event.start.strftime("%H:%M")
        ending_time = self.event.end.strftime("%H:%M")

        embed = Embed(title="Voulez vous confirmer?",
                      description=f"Etes vous sur de vouloir reserver le rendez-vous de {self.event.day} de {starting_time} a {ending_time}?",
                      color=Colour.blue())
        
        confirmView = ConfirmMeetingView(self.event, values)
        await interaction.response.send_message(embed=embed, view=confirmView, ephemeral=True)
        self.stop()

    async def on_timeout(self):
        await self.event.cancel_rdv()
        self.stop()


class ConfirmMeetingView(ui.View):
    def __init__(self, event: CalendarEvent, infos: dict = {}):
        super().__init__(timeout = 60)
        self.value = None
        self.event = event
        self.infos = infos

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @ui.button(label="Confirmer", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:  
        description = ""
        for info in self.infos:
            description += f"{info}: {self.infos[info]}\n\n"

        user = interaction.user
        """overwrites: dict[Role | Member, PermissionOverwrite] = {
            interaction.guild.default_role: PermissionOverwrite(view_channel=False),
            user: PermissionOverwrite(view_channel=True), 
            interaction.guild.get_role(MODERATION_ROLE): PermissionOverwrite(view_channel=True)
        } """

        self.event.summary = f"Rendez-vous ({user})"
        self.event.description = description
        self.event.reminders = {
                            'useDefault': False,
                            'overrides': [
                                {'method': 'popup', 'minutes': 10},
                            ], 
                            }

        channel = None
        content = user.mention  
        meetView = MeetingView()
        message = None
        for rdv_channel in interaction.channel.category.channels:  
            if str(rdv_channel.name)[:3] == "rdv":
                author = await MeetingView().get_thread_author(rdv_channel)  
                if author == interaction.user:
                    channel = rdv_channel
                    content = None
                    meetView = None
                    history = channel.history(oldest_first=True, limit=1)  
                    history_flat = await history.flatten()
                    message = history_flat[0]  
                    await message.edit(view=MeetingView()) 

        for rdv_channel in utils.get(interaction.guild.categories, name="Archives").channels: 
            if str(rdv_channel.name)[:3] == "rdv":
                author = await MeetingView().get_thread_author(rdv_channel)  
                if author == interaction.user:
                    channel = rdv_channel
                    content = None
                    meetView = None
                    await channel.edit(category=interaction.channel.category, sync_permissions=True)
                    await channel.set_permissions(author, view_channel=True)
                    await channel.purge(limit=1) 
                    history = channel.history(oldest_first=True, limit=1)  
                    history_flat = await history.flatten()
                    message = history_flat[0]  
                    await message.edit(view=MeetingView()) 

        if not channel:
            channel = await interaction.guild.create_text_channel(name=f"rdv-{str(interaction.user).replace(' ', '')}", category=interaction.channel.category) 
            await channel.set_permissions(user, view_channel=True) 
            

        self.event.location = channel.id
        calendar.update(self.event.id, self.event.build())

        embed = Embed(
                title=f"Rendez-vous de {user}",
                description=f"{self.event.day} de {self.event.start.strftime('%H:%M')} a {self.event.end.strftime('%H:%M')}",
                colour=Colour.blue(),
            )
        embed.set_footer()

        
        
        msg = await channel.send(content, view=meetView, embed=embed) 
        await msg.pin()
        embed = Embed(
                title="Rendez-vous pris!",
                description="Le rendez-vous a bien été reservé!",
                color=Colour.green()
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.value = True
        self.stop()

        if not message:
            message = msg

        await MeetingView().schedule_alert(interaction, self.event, message) 
            

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        await self.event.cancel_rdv(interaction)
        self.value = False
        self.stop()

    async def on_timeout(self) -> None:
        if not self.value:
            await self.event.cancel_rdv()
        self.stop()


class MeetingView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def schedule_alert(self, interaction: Interaction, event: CalendarEvent, message: PartialInteractionMessage) -> None:
        now = datetime.now()
        then = event.start - timedelta(minutes=10)
        wait = int((then-now).total_seconds())
        wait = 0 if wait < 0 else wait
        if interaction.guild:
            await sleep(wait)
            rdv_channel = interaction.guild.get_channel(int(event.location))
            if str(rdv_channel.category) == "Rendez-vous":  
                if event.check_event():
                    now = datetime.now()
                    wait = int((event.start-now).total_seconds())
                    if wait > 0:
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

            rdv_channel = interaction.guild.get_channel(int(event.location))
            if str(rdv_channel.category) == "Rendez-vous":  
                if event.check_event():
                        
                        embed = Embed(
                            title="Le rendez-vous a commencé",
                            color=Colour.green()
                        )

                        await rdv_channel.send("@here", embed=embed) 
                        await interaction.user.add_roles(interaction.guild.get_role(CLIENT_ROLE))  
                        now = datetime.now()
                        then = event.end
                        wait = int((then-now).total_seconds())
                        wait = 0 if wait < 0 else wait
                        await sleep(wait)
                        embed = Embed(
                            title="Le rendez-vous est fini",
                            color=Colour.red()
                        )

                        await rdv_channel.send("@here", embed=embed) 
                        for button in self.children:
                            button.disabled = False  
                        await message.edit(view=self)  
                else:
                    embed = Embed(
                        title="Le rendez-vous a été annulé",
                        color=Colour.red()
                    )

                    await rdv_channel.send("@here", embed=embed)  

    async def get_thread_author(self, channel: TextChannel) -> Union[Member, User]:
        history = channel.history(oldest_first=True, limit=1)
        history_flat = await history.flatten()
        user: Union[Member, User] = history_flat[0].mentions[0]
        return user

    async def close_help_thread(self, interaction: Interaction) -> None:
        embed_reply = Embed(
            title="Ce salon a été fermé",
            colour=Colour.dark_theme(),
        )
        channel = interaction.channel
        channel_author = await self.get_thread_author(channel) 
        closed_by = interaction.user

        # Send the closing message to the help thread
        await channel.send(embed=embed_reply) 
        await channel.set_permissions(channel_author, read_messages=False) 

        # Send log
        embed_log = Embed(
            title=":x: Rendez-vous férmé",
            description=(
                f"{channel.mention}\n\nRendez vous crée par {channel_author.mention} a été férmé par {closed_by.mention}.\n\n" 
                f"Createur: `{channel_author} ({channel_author.id})`\n"
                f"Férmé par: `{closed_by} ({closed_by.id})`" 
            ),
            colour=0xDD2E44,  # Red
        )

        await channel.edit(category=utils.get(channel.guild.categories, name="Archives"), sync_permissions=True) 
        await utils.get(interaction.guild.channels, name="logs").send(embed=embed_log) 


    @ui.button(label="Reprendre un RDV", style=ButtonStyle.primary, custom_id=f"take_other_meet", disabled=True)
    async def take_other_meet(self, button: Button, interaction: Interaction) -> None:
        embed = Embed(title="Engagement", description="En cliquant sur accepter vous vous engager a payer apres le rendez-vous", colour=Colour.blue())
        await interaction.response.send_message(embed=embed, view=AcceptConditionsView(), ephemeral=True)
    
    @ui.button(label="Fermer", style=ButtonStyle.red, custom_id=f"meet_close_button")
    async def meet_close_button(self, button: Button, interaction: Interaction) -> None:
        for children in self.children:
            children.disabled = True  
        await interaction.response.edit_message(view=self)
        await self.close_help_thread(interaction)


class AcceptConditionsView(ui.View):
    def __init__(self):
        super().__init__(timeout = 60*2)
        self.value = None

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @ui.button(label="Accepter", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:
        await TakeMeetingView().take_meeting(interaction)
        self.value = True
        self.stop()

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        self.value = False
        self.stop()


class RetakeMeetingView(ui.View):
    def __init__(self, event):
        super().__init__(timeout = None)
        self.value = None
        self.event = event

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @ui.button(label="Confirmer", style=ButtonStyle.green)
    async def confirm(self, button: ui.Button, interaction: Interaction) -> None:
        await TakeMeetingView().take_meeting(interaction)
        self.value = True
        self.stop()

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label="Annuler", style=ButtonStyle.danger)
    async def cancel(self, button: ui.Button, interaction: Interaction) -> None:
        await self.event.cancel_rdv(interaction, False)
        self.value = False
        self.stop()


class Meetings(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.client.loop.create_task(self.create_views())

    async def create_views(self):
        self.client.rdv_view_set = True 
        self.client.add_view(TakeMeetingView())
        self.client.add_view(MeetingView())
    
    @slash_command(name="prepare")
    async def prepare(self, interaction: Interaction):
        meetingEmbed = Embed(title="Prise de Rendez-Vous",
                             description="Pour prendre un rendez-vous",
                             color=Colour.blue())

        await interaction.channel.purge() 
        await interaction.channel.send(embed=meetingEmbed, view=TakeMeetingView()) 

    @slash_command(name="clear", description="Pour purger le salon")
    async def clear(
            self,
            interaction: Interaction,
            channel: TextChannel = SlashOption(name="channel", description="Choisissez un salon", required=False),
            limit: int = SlashOption(name="limit", description="Choisissez une limite", required=False)) -> None:

        if not channel and isinstance(interaction.channel, TextChannel):
            channel = interaction.channel
        
        await channel.purge(limit=int(limit) if limit else None)
        
        embed = Embed(title="Le salon a été purgé", color=nextcord.Colour.green()
                            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


    @slash_command(name="clear_events", description="Pour purger le salon")
    async def clear_events(self, interaction: Interaction) -> None:
        
        events_result = calendar.list()
        events = events_result.get('items', [])
        deleted = []
        for event in events:
            event = CalendarEvent(event)
            deleted.append(event.summary)
            calendar.delete(event.id)
            
        embed = Embed(
            title="Les events suivant ont été purgés:",
            description='\n'.join(deleted),
            color=Colour.green()
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

def setup(client):
    client.add_cog(Meetings(client))
