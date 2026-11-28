"""Batocera locale precedence, English UI/options, and unchanged profile values."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_i18n as lang
from partydeck_couch import App,BO1_TABS,STORAGE_GAME_ROW,STORAGE_OPTIONS,control_label,context_hints,fields,label_value
from partydeck_profiles import defaults,save_profile,read_profile,profile_path,edit_profile_legacy,edit_anchor,edit_soh_graphics
from partydeck_anchor import defaults as anchor_defaults, graphics_defaults
from partydeck_storage import DEFAULTS,human,preflight
from partydeck_catalog import COMMON

for language, titles in (
        ('fr', ('Ultrawide en partage horizontal à deux (test)', 'Zoom de la caméra · Résolution classique',
                'Grandes polices', 'Taille de la police du chat', 'Disposition du HUD Ultrawide')),
        ('en', ('Ultrawide for two players in horizontal split (experimental)', 'Camera zoom · Legacy resolution',
                'Large Font Mode', 'Chat font size', 'Ultrawide HUD layout'))):
    lang.set_language(language)
    d2r_app = SimpleNamespace(model=SimpleNamespace(data={'adapter': 'd2rloader'}))
    assert App.available_tabs(d2r_app) == (0, 1, 2)
    assert tuple(label for _, label, _ in fields(2, 'd2rloader')) == titles
    assert label_value('d2rloader.legacy_resolution', '640x480') == '640×480'
    assert label_value('d2rloader.large_font', 'keep') == ('Réglage du jeu' if language == 'fr' else 'In-game setting')
    assert label_value('d2rloader.chat_font', 'extra_large') == ('Très grande' if language == 'fr' else 'Extra large')
    assert label_value('d2rloader.ultrawide_hud', 'full') == ('Pleine largeur' if language == 'fr' else 'Full width')

for language, music, locale in (('fr', 'Musique uniquement pour J1', 'Français'),
                                ('en', 'Music on player 1 only', 'French')):
    lang.set_language(language)
    assert dict((key, title) for key, title, _ in fields(3, 'dont-starve-together'))['dst.music_j1_only'] == music
    assert label_value('dst.language', 'french') == locale

for language, resume in (('fr', 'Relancer automatiquement le dernier monde'),
                         ('en', 'Automatically resume the last world')):
    lang.set_language(language)
    assert fields(1, 'dont-starve-together') == [('dst.resume_last_world', resume, [False, True])]
    dst_app = SimpleNamespace(model=SimpleNamespace(data={'adapter': 'dont-starve-together'}))
    assert 1 in App.available_tabs(dst_app)

for language, title, remove in (('fr', 'Jeu introuvable', 'Retirer le jeu'),
                                ('en', 'Game not found', 'Remove the game')):
    lang.set_language(language)
    assert lang.tr('Jeu introuvable') == title
    assert dict(context_hints('relink', 'keyboard'))['search'] == remove

for language,host,automatic,campaign in (
        ('fr','Joueur hôte','Héberger et rejoindre automatiquement','Choisir dans le jeu'),
        ('en','Host player','Host and join automatically','Choose in game')):
    lang.set_language(language)
    for adapter in ('borderlands2','sm64coopdx','l4d2-goldberg'):
        available=[field for tab in range(5) for field in fields(tab,adapter)]
        assert next(label for key,label,choices in available if key.endswith('.host_player'))==host
    assert lang.tr('Héberger et rejoindre automatiquement')==automatic
    assert label_value('l4d2.campaign','menu')==campaign
    assert label_value('l4d2.campaign','c1m1_hotel')=='1 · Dead Center'
    assert label_value('l4d2.campaign','c14m1_junkyard')=='14 · The Last Stand'
    l4d2_options={key for key,_,_ in fields(2,'l4d2-goldberg')}
    assert {'l4d2.campaign','l4d2.campaign_mode'}.isdisjoint(l4d2_options)
from partydeck_bo2 import MODES as BO2_MODES

for language, multiplayer, original, catalog, horizontal, automatic in (
        ('fr', 'Multijoueur', 'Lancement d’origine', 'LAN expérimental', 'Rendu en partage horizontal', 'Rejoindre automatiquement la partie de J1'),
        ('en', 'Multiplayer', 'Original launch', 'Experimental LAN', 'Horizontal split-screen rendering', 'Automatically join P1’s match')):
    lang.set_language(language)
    assert fields(1, 'black-ops-2') == [
        ('bo2.open_custom_lobby', 'Ouvrir Parties personnalisées au démarrage' if language == 'fr'
         else 'Open Custom Games at startup', [False, True]),
        ('bo2.automatic_join', automatic, [True, False]),
        ('bo2.language', 'Langue du jeu' if language == 'fr' else 'Game language', ['keep', 'french', 'english']),
        ('bo2.horizontal_render', horizontal, ['native', '720p', 'standard']),
        ('bo2.zombie_bots', 'Bots alliés · Zombies' if language == 'fr' else 'Friendly bots · Zombies', list(range(4)))]
    assert lang.tr(BO2_MODES['original']) == original
    assert label_value('bo2.language', 'french') == ('Français' if language == 'fr' else 'French')
    assert label_value('bo2.language', 'english') == ('Anglais' if language == 'fr' else 'English')
    bo1_app = SimpleNamespace(model=SimpleNamespace(data={'adapter': 'black-ops-1'}))
    assert App.available_tabs(bo1_app) == (0, 1, 2, 3)
    assert tuple(map(lang.tr, BO1_TABS)) == ('Session', 'Options', 'Affichage' if language == 'fr' else 'Display', 'Bots')
    assert fields(1, 'black-ops-1') == [
        ('bo1.open_custom_lobby', 'Ouvrir le salon privé au démarrage' if language == 'fr'
         else 'Open Private Match at startup', [False, True]),
        ('bo1.automatic_join', automatic, [True, False]),
        ('bo1.language', 'Langue du jeu' if language == 'fr' else 'Game language', ['keep', 'french', 'english']),
    ]
    assert fields(2, 'black-ops-1') == [
        ('bo1.horizontal_render', horizontal, ['native', '720p', 'standard']),
        ('bo1.horizontal_fov', 'Champ de vision en partage horizontal' if language == 'fr'
         else 'Horizontal split-screen field of view', [0, *range(65, 111, 5)]),
        ('bo1.vertical_native', 'Résolution native en vertical (test)' if language == 'fr'
         else 'Native vertical resolution (experimental)', [False, True]),
        ('bo1.vertical_fov', 'Champ de vision en partage vertical' if language == 'fr'
         else 'Vertical split-screen field of view', [0, *range(65, 111, 5)]),
    ]
    assert label_value('bo1.vertical_fov', 100) == '100°'
    assert label_value('bo1.horizontal_fov', 85) == '85°'
    assert label_value('bo1.horizontal_fov', 0) == ('Réglage du jeu' if language == 'fr' else 'In-game setting')
    assert label_value('bo1.vertical_fov', 0) == ('Réglage du jeu' if language == 'fr' else 'In-game setting')
    assert fields(3, 'black-ops-1') == [
        ('bo1.private_bots', 'Bots en chacun-pour-soi' if language == 'fr' else 'Free-for-all bots', list(range(13))),
        ('bo1.team_total_bots', 'Total de bots en équipe · Équilibrage auto' if language == 'fr'
         else 'Total team bots · Auto balance', list(range(13))),
        ('bo1.allies_bots', 'Bots alliés · Modes en équipe' if language == 'fr' else 'Allies bots · Team modes', list(range(7))),
        ('bo1.axis_bots', 'Bots de l’Axe · Modes en équipe' if language == 'fr' else 'Axis bots · Team modes', list(range(7))),
        ('bo1.zombie_bots', 'Bots alliés · Zombies' if language == 'fr' else 'Friendly bots · Zombies', list(range(4))),
    ]
    assert label_value('bo1.team_total_bots', 0) == ('Par équipe (manuel)' if language == 'fr' else 'Per team (manual)')
    assert label_value('bo1.team_total_bots', 6) == '6'
    bo1_app.tab = 3
    bo1_app.model.celeste_skins = bo1_app.model.story_skins = ()
    for total in (0, 6):
        bo1_app.model.data['bo1'] = {'team_total_bots': total}
        assert App.current_fields(bo1_app) == [row for row in fields(3, 'black-ops-1')
                                                 if not total or row[0] not in ('bo1.allies_bots', 'bo1.axis_bots')]
    assert lang.tr('Choisir le mode de jeu') == ('Choisir le mode de jeu' if language == 'fr' else 'Choose the game mode')
    assert label_value('adapter', 'ocarina-story-coop') == 'Ocarina of Time · Story Co-op'
    assert 'ocarina-story-coop' in dict((key, values) for key, _, values in fields(0, 'ocarina-story-coop'))['adapter']
    assert label_value('bo2.horizontal_render', 'native') == {
        'fr': 'Résolution de chaque moitié', 'en': 'Match each half of the screen'}[language]
    assert label_value('bo2.horizontal_render', '720p') == {
        'fr': 'Ultrawide · hauteur minimale 720p', 'en': 'Ultrawide · 720p minimum height'}[language]
    assert lang.tr('Black Ops II {p0} : rendu demandé {p1}, écran virtuel {p2}, fenêtre {p3}.',
                   p0='J1', p1='1920x540', p2='2560x720', p3='1920x540') == {
        'fr': 'Black Ops II J1 : rendu demandé 1920x540, écran virtuel 2560x720, fenêtre 1920x540.',
        'en': 'Black Ops II J1: requested render size 1920x540, virtual display 2560x720, window 1920x540.',
    }[language]
    assert lang.tr('Black Ops II {p0} : connexion confirmée par J1.', p0='J2') == {
        'fr': 'Black Ops II J2 : connexion confirmée par J1.',
        'en': 'Black Ops II J2: P1 confirmed the connection.',
    }[language]
    assert lang.tr('Black Ops II {p0} : attente de l’initialisation de {p1}.', p0='J2', p1='J1') == {
        'fr': 'Black Ops II J2 : attente de l’initialisation de J1.',
        'en': 'Black Ops II J2: waiting for J1 to initialize.',
    }[language]
    assert lang.tr(BO2_MODES['plutonium-mp']) == f'{multiplayer} · Plutonium LAN'
    assert lang.tr(BO2_MODES['plutonium-zm']) == 'Zombies · Plutonium LAN'
    assert next(game for game in COMMON if game.id == 'bo2').stem == f'Black Ops II · {catalog}'
lang.set_language('fr')

for language, automatic, skin, default_skin in (
        ('fr', 'Créer et rejoindre le groupe automatiquement', 'J1 · Skin', 'Link standard'),
        ('en', 'Automatically create and join the party', 'Player 1 · Skin', 'Default Link')):
    lang.set_language(language)
    network = {key: label for key, label, _ in fields(1, 'ocarina-story-coop')}
    assert network['ocarina-story-coop.automatic'] == automatic
    time_mode = 'ocarina-story-coop.time_mode'
    assert network[time_mode] == ('Cycle jour/nuit' if language == 'fr' else 'Day/night cycle')
    assert label_value(time_mode, 'original') == (
        'Cycle d’origine par joueur' if language == 'fr' else 'Original cycle per player')
    for key, fr, en in (('rupees', 'Partager les rubis', 'Share rupees'),
                        ('ammo', 'Partager les munitions', 'Share ammo'),
                        ('healing', 'Partager les PV', 'Share healing')):
        assert network[f'ocarina-story-coop.consumables.{key}'] == (fr if language == 'fr' else en)
    player_fields = fields(2, 'ocarina-story-coop', story_skins=['linkle'])
    assert player_fields[1][:2] == ('ocarina-story-coop.skins.0', skin)
    assert len(player_fields[1][2]) == 22 and 'linkle' in player_fields[1][2]
    assert label_value(player_fields[1][0], 'link') == default_skin
    assert label_value(player_fields[1][0], '') == ('Mods du jeu' if language == 'fr' else 'Game mods')
    assert label_value(player_fields[1][0], 'linkle') == 'Linkle by DanatheElf'
    assert lang.tr('Story Co-op {p0} : fenêtre du jeu absente, relance de ce joueur.', p0='J1') == {
        'fr': 'Story Co-op J1 : fenêtre du jeu absente, relance de ce joueur.',
        'en': 'Story Co-op J1: game window missing, restarting this player.',
    }[language]
    assert not any(row[0].endswith('.freecam') for row in player_fields)
    assert App.available_tabs(SimpleNamespace(model=SimpleNamespace(data={'adapter': 'ocarina-story-coop'}))) == (
        0, 1, 2, 4, 3)
    gameplay = fields(4, 'ocarina-story-coop')
    assert gameplay[0][:2] == ('ocarina-story-coop.freecam',
        'Caméra libre au stick droit' if language == 'fr' else 'Free camera on right stick')
    distance_mode, distance = gameplay[1:3]
    assert distance_mode == ('ocarina-story-coop.camera_distance_mode',
                             'Distance de la caméra libre' if language == 'fr' else 'Free camera distance',
                             ['keep', 'game', 'fixed'])
    assert distance == ('ocarina-story-coop.camera_distance',
                        'Distance fixe de la caméra libre' if language == 'fr' else 'Fixed free camera distance',
                        None)
    assert label_value(distance_mode[0], 'game') == (
        'Suivre la distance du jeu' if language == 'fr' else 'Follow the game’s camera distance')
    assert label_value(distance_mode[0], 'fixed') == ('Distance fixe' if language == 'fr' else 'Fixed distance')
    assert [row[0].split('.')[-1] for row in gameplay[3:-1]] == ['third_x', 'third_y', 'first_x', 'first_y']
    assert gameplay[-2][1] == ('Vue 1re personne et visée · inverser l’axe vertical' if language == 'fr'
                                else 'First person and aiming · invert vertical axis')
    assert gameplay[-1][:2] == ('ocarina-story-coop.remove_black_bars',
        'Supprimer les bandes noires en cinématique et en visée' if language == 'fr'
        else 'Remove black bars in cutscenes and while targeting')
    for key, _, choices in gameplay[3:]:
        assert choices == ['keep', 'on', 'off']
        assert label_value(key, 'keep') == ('Conserver' if language == 'fr' else 'Keep current')
    assert [field[1:] for field in fields(3, 'ocarina-story-coop')] == [
        field[1:] for field in fields(3, 'soh-anchor')]
lang.set_language('fr')

for language, title, message in (
        ('fr', 'Windows Party · Lancement interrompu', 'Manettes détectées : 1. Manettes nécessaires : 2.'),
        ('en', 'Windows Party · Launch stopped', 'Controllers detected: 1. Controllers required: 2.')):
    lang.set_language(language)
    assert lang.tr('Windows Party · Lancement interrompu') == title
    assert lang.tr('Manettes détectées : {p0}. Manettes nécessaires : {p1}.', p0=1, p1=2) == message
lang.set_language('fr')

# Surface the launcher's reason rather than its long argv, in either UI locale.
for selected,prefix in (('fr','Enregistrement impossible : '),('en','Could not save: ')):
    lang.set_language(selected)
    reason='Session is still running.'
    failed=SimpleNamespace(model=SimpleNamespace(data=True,save=Mock(
        side_effect=subprocess.CalledProcessError(1,['long','command'],stderr=reason+'\n'))),toast=Mock())
    assert App.save(failed) is False
    failed.toast.assert_called_once_with(prefix+reason)
lang.set_language('fr')

for locale in ('fr','fr_FR','fr-FR','FR_ca.UTF-8','fr_BE@euro',"'fr_FR'"):
    assert lang.locale_language(locale)=='fr'
for locale in ('en_US','de_DE','es_ES','zh_CN','C.UTF-8','','frr_FR','france'):
    assert lang.locale_language(locale)=='en'

for selected,labels in (('fr',('Langue du jeu','Activer la manette en jeu','Français','Conserver')),
                        ('en',('Game language','Enable gamepad in game','French','Keep current'))):
    lang.set_language(selected)
    assert [title for _,title,_ in fields(2,'l4d2-goldberg')][:2]==list(labels[:2])
    assert label_value('l4d2.language','french')==labels[2]
    assert label_value('l4d2.language','keep')==labels[3]

for language,title in (('fr','RUNNER WINE'),('en','WINE RUNNER')):
    lang.set_language(language)
    assert lang.tr('RUNNER WINE')==title
    hint=lang.tr('Runner propre à Windows Party. Auto : utiliser le runner du jeu Windows d’origine.')
    assert ('original Windows' in hint) if language=='en' else ('d’origine' in hint)

for language,label in (('fr','IP LAN du PC (auto : détection)'),('en','PC LAN IP (auto: detect)')):
    lang.set_language(language)
    assert next(title for key,title,_ in fields(1,'nfsmw-lan') if key=='nfsmw.host')==label
    assert fields(1,'nfsmw-lan')[0][1]==('LAN privé local (sans Internet)' if language=='fr' else 'Local private LAN (no Internet)')

for language,title,choice in (('fr','GPU de rendu','Configuration système'),('en','Rendering GPU','System configuration')):
    lang.set_language(language)
    assert next(label for key,label,_ in fields(0) if key=='gpu')==title
    assert label_value('gpu','system')==choice

for language,prefix in (('fr','Contrôles virtuels toolbox'),('en','Toolbox virtual controls')):
    lang.set_language(language)
    assert lang.tr('Contrôles virtuels toolbox : {p0}',p0='test').startswith(prefix)

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);conf=root/'batocera.conf';es=root/'es_settings.cfg'
    env={'LANG':'fr_FR.UTF-8'}
    def detect(environment=env):
        return lang.detect_language(environment,conf,es)
    with patch.object(lang.shutil,'which',return_value='/bin/batocera-settings-get'):
        for selected,expected in (('fr_FR\n','fr'),('de_DE\n','en'),('es_ES\n','en'),('en_US\n','en')):
            with patch.object(lang.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=selected)) as run:
                assert detect()==expected
                assert run.call_args.args[0]==['/bin/batocera-settings-get','system.language']
                assert run.call_args.kwargs['timeout']==2
        conf.write_text('#system.language=en_US\nsystem.language=de_DE\nsystem.language=fr_CA\n')
        with patch.object(lang.subprocess,'run',side_effect=subprocess.TimeoutExpired('settings',2)):
            assert detect()== 'fr'
    with patch.object(lang.shutil,'which',return_value=None):
        conf.write_text('system.language=de_DE\n')
        assert detect()=='en'  # Batocera wins over a French SSH environment.
        conf.write_text('system.language=fr_FR\n')
        assert detect({'LANG':'en_US'})=='fr'
        conf.unlink();es.write_text('<config><string name="Language" value="it_IT"/></config>')
        assert detect()=='en'
        es.write_text('<config><string name="Language" value="fr_FR"/></config>')
        assert detect({'LANG':'en_US'})=='fr'
        es.write_text('<invalid')
        assert detect({'LC_ALL':'de_DE','LANG':'fr_FR'})=='en'
        assert detect({'LANGUAGE':'fr_FR:en_US'})=='fr'
        assert detect({})=='en'
        assert detect({'PARTYDECK_LANGUAGE':'en','LANG':'fr_FR'})=='en'
    # Every translation keeps the same format placeholders.
    import string
    for source,target in lang.EN.items():
        names=lambda s: {f[1] for f in string.Formatter().parse(s) if f[1] is not None}
        assert names(source)==names(target),source
    lang.set_language('en')
    assert lang.tr('--field=Joueurs:CB')=='--field=Players:CB'
    assert lang.tr('--button=Annuler:1')=='--button=Cancel:1'
    assert lang.tr('--field=J{p0} — nom',p0=2)=='--field=Player 2 — name'
    assert control_label('ok','keyboard')=='Enter'
    assert control_label('back','keyboard')=='Esc'
    assert control_label('add','keyboard')=='Ins'
    assert control_label('ok','ps')=='Cross'
    assert ('save','Save') in context_hints('main','ps')
    assert ('tabs','Pages · hold') in context_hints('browser','ps')
    assert label_value('input','clavier-j1')=='Keyboard/mouse · P1'
    assert label_value('borderlands2.preset','medium')=='Medium'
    assert label_value('borderlands2.vsync','on')=='Enabled'
    assert label_value('borderlands2.vsync','off')=='Disabled'
    assert label_value('borderlands2.vsync','keep')=='Keep current'
    assert [key for key,_,_ in fields(1,'borderlands2')]==['borderlands2.preset','borderlands2.vsync','borderlands2.physx']
    assert label_value('borderlands2.names.0','')=='Keep current'
    assert label_value('borderlands2.names.0','Joueur français')=='Joueur français'
    assert fields(2,'borderlands2')[0][1]=='Player 1 · Name'
    assert dict((key,title) for key,title,_ in fields(2,'borderlands2'))['borderlands2.automatic']=='Automatically join the host (private SDK)'
    assert label_value('anchor.locations',1)=='Team only'
    assert label_value('anchor.graphics.texture_filter',0)=='N64 three-point'
    assert label_value('anchor.names.0','Enregistrer')=='Enregistrer'
    assert fields(2,'sm64coopdx')[0][1]=='Free camera'
    assert fields(1,'l4d2-goldberg')[0][1]=='Player 1 · Name'
    assert label_value('l4d2.names.0','Joueur français')=='Joueur français'
    assert fields(3,'sm64coopdx')[0][1]=='Game language'
    assert label_value('sm64coopdx.language','French')=='French'
    assert label_value('sm64coopdx.texture_filtering',2)=='N64 three-point'
    assert label_value('sm64coopdx.coop_draw_distance',6)=='Infinite'
    assert label_value('sm64coopdx.names.0','Joueur français')=='Joueur français'
    assert human(1024**3)=='1.0 GiB'
    assert 'shared profile' in COMMON[0].stem
    # Create French-named user data before switching the configurator to English.
    lang.set_language('fr')
    assert ('tabs','Pages · maintenir') in context_hints('browser','xbox')
    assert fields(2,'sm64coopdx')[0][1]=='Caméra libre'
    assert fields(1,'l4d2-goldberg')[0][1]=='J1 · Nom'
    assert label_value('sm64coopdx.language','French')=='Français'
    assert fields(2,'borderlands2')[0][1]=='J1 · Nom'
    assert dict((key,title) for key,title,_ in fields(2,'borderlands2'))['borderlands2.automatic']=='Connexion automatique à l’hôte (SDK privé)'
    rom=root/'Enregistrer.wsquashfs';rom.touch()
    data=defaults(rom);data.update(adapter='soh-anchor',anchor=anchor_defaults())
    data['anchor'].update(room='Annuler',names=['Enregistrer','Équipe','Moyen','Joueur4'])
    save_profile(root,rom,data)
    original=profile_path(root,rom).read_bytes()
    with patch('partydeck_couch.detect_language',return_value='en'):
        app=App(root,rom,windowed=True)
    assert lang.get_language()=='en' and ''.join(app.keys[0])=='qwertyuiop'
    rendered=[]
    original_text=app.text
    def record(value,*args,**kwargs):
        rendered.append(str(value));return original_text(value,*args,**kwargs)
    with patch.object(app,'text',side_effect=record):
        for tab in range(4):
            app.tab=tab;app.row=0;app.draw()
        app.tab=2;app.draw()
        assert 'Player 1 · Name' in rendered and 'Enregistrer' in rendered
        assert 'Network' in rendered and 'Graphics & audio' in rendered
        assert 'Master volume (%)' in [title for _,title,_ in fields(3)]
        app.edit('Player name','Enregistrer',lambda value:None);app.draw()
        assert {'Shift','Space','Backspace','Clear','Done'} <= set(rendered)
        app.action('back');app.request_remove();app.draw()
        assert 'UNLINK THIS GAME?' in rendered
        app.action('back')
        app.storage_open=True;app.storage_config=dict(DEFAULTS);app.draw()
        assert 'WINDOWS PARTY STORAGE' in rendered and 'Total caches (MiB)' in rendered
        app.storage_row = next(i for i, (key, _) in enumerate(STORAGE_OPTIONS) if key == 'keep_latest_runner')
        for language, title, hint in (
                ('fr', 'Supprimer les bottles des anciens runners',
                 'Jeux .wsquashfs · les sauvegardes internes aux anciennes bottles sont supprimées.'),
                ('en', 'Delete bottles from previous runners',
                 '.wsquashfs games · saves stored inside old bottles are deleted.')):
            lang.set_language(language)
            rendered.clear()
            app.draw_storage()
            assert {title, hint} <= set(rendered)
        for language, expected in (
                ('fr', ('Wine-bottles uniquement', 'Wine-bottles + sauvegardes', 'Supprimer définitivement')),
                ('en', ('Wine bottles only', 'Wine bottles + saves', 'Delete permanently'))):
            lang.set_language(language)
            rendered.clear()
            app.storage_result = dict(games=[dict(name=rom.stem, rom=str(rom))])
            app.storage_row = STORAGE_GAME_ROW
            app.storage_action('ok')
            app.draw_game_cleanup()
            app.game_cleanup_action('ok')
            app.draw_game_cleanup()
            assert set(expected) <= set(rendered)
            app.game_cleanup_action('back')
        app.storage_result = None
        app.storage_open=False
    assert profile_path(root,rom).read_bytes()==original
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
        assert app.save()
    after=read_profile(root,rom)
    assert after['anchor']['names']==data['anchor']['names'] and after['anchor']['room']=='Annuler'
    assert after['input']=='auto' and after['split']=='horizontal'
    # QWERTY uses translated command labels, but inserts literal characters.
    typed=[];app.edit('Player name','',typed.append);app.action('ok')
    assert app.keyboard['value']=='q'
    app.action('save');assert typed==['q']
    # Legacy editor choices translate back to stable, existing schema tokens.
    with patch('partydeck_profiles.yad',return_value=Mock(returncode=0,stdout='Automatic\x1fVertical\x1fKeyboard/mouse · P1\x1fFALSE\x1f\n')):
        assert edit_profile_legacy(root,rom)
    after=read_profile(root,rom)
    assert after['players']=='auto' and after['split']=='vertical' and after['input']=='clavier-j1'
    values=['TRUE','TRUE','Annuler','anchor.hm64.org','43383','shipofharkinian.json',
            'Enabled + friendly fire','Everyone','Nobody','FALSE',
            'Enregistrer','default','Équipe','default','Moyen','default','Joueur4','default']
    with patch('partydeck_profiles.yad',return_value=Mock(returncode=0,stdout='\x1f'.join(values)+'\x1f\n')):
        assert edit_anchor(after)
    assert after['anchor']['pvp']==2 and after['anchor']['names'][0]=='Enregistrer'
    with patch('partydeck_profiles.yad',return_value=Mock(returncode=0,stdout='1.25\x1f4\x1fTRUE\x1fLinear\x1fTRUE'+'\x1f'*6+'\n')):
        assert edit_soh_graphics(after['anchor'])
    assert after['anchor']['graphics']['texture_filter']==1
    with patch('partydeck_storage.disks',return_value=[dict(path='/userdata',free=0,total=1024**3)]):
        try:
            preflight(root,root,dict(DEFAULTS,auto_clean=False))
            raise AssertionError('ignored disk threshold')
        except RuntimeError as error:
            assert str(error).startswith('Not enough disk space')
    app.pg.quit()
    with patch('partydeck_couch.detect_language',return_value='fr'):
        app=App(root,rom,windowed=True)
    assert ''.join(app.keys[0])=='azertyuiop' and control_label('ok','keyboard')=='Entrée'
    assert read_profile(root,rom)['anchor']['names']==data['anchor']['names']
    app.pg.quit()

print('Langues : priorité Batocera/SSH, FR sinon EN, options de jeux, clavier, stockage et données conservées vérifiés.')

# Global screen/GPU settings are translated without changing connector IDs.
from partydeck_display import Output,output_label
for language in ('fr','en'):
    lang.set_language(language)
    assert lang.tr('PARAMÈTRES')==('PARAMÈTRES' if language=='fr' else 'SETTINGS')
    assert lang.tr('Écran des jeux')==('Écran des jeux' if language=='fr' else 'Game display')
    assert lang.tr('GPU par défaut')==('GPU par défaut' if language=='fr' else 'Default GPU')
    assert output_label([Output('DP-4',(1920,0,1920,1080))],'DP-4')=='DP-4 · 1920×1080 · 1920,0'
    assert ('unavailable' if language=='en' else 'indisponible') in output_label([],'eDP-1')

# Bottle storage surfaces are available in both languages.
for locale,label in (('fr','Sauvegardes'),('en','Saves')):
    lang.set_language(locale)
    assert lang.tr('Sauvegardes {p0} · Bottles {p1} · Runtime {p2}',p0=1,p1=2,p2=3).startswith(label)
    assert lang.tr('Bottle encore montée : {p0}',p0='test').startswith('Bottle encore' if locale=='fr' else 'Bottle is still')
# Hollow Knight network/co-op controls and addon identifiers are bilingual.
for language,title,coop in (('fr','Héberger et rejoindre automatiquement','PV partagés des ennemis · ESoulLink'),('en','Host and join automatically','Shared enemy HP · ESoulLink')):
    lang.set_language(language)
    assert fields(1,'hollowknight-hkmp')[0][1]==title
    assert fields(2,'hollowknight-hkmp')[-2][1]==coop
    assert label_value('hkmp.enemy_health','keep')==('Conserver' if language=='fr' else 'Keep current')
    assert label_value('hkmp.enemy_ghosts','on')==('Activé' if language=='fr' else 'Enabled')
    assert lang.tr('Hollow Knight · coop HKMP')==('Hollow Knight · coop HKMP' if language=='fr' else 'Hollow Knight · HKMP co-op')

# HKMultiplayer uses a separate native API adapter and keeps assigned HIDRAW.
for language,controller,world in (
        ('fr','Désactiver l’entrée native · conserver HIDRAW','Dernier monde joué'),
        ('en','Disable native input · keep HIDRAW','Most recently played world')):
    lang.set_language(language)
    assert fields(3,'hollowknight-hkmultiplayer')[0][1]==controller
    assert label_value('hkmultiplayer.world','latest')==world
    assert label_value('hkmultiplayer.host.sharedMap',1)==('Activé' if language=='fr' else 'Enabled')
    for tab in (1,2,3):
        for key,label,choices in fields(tab,'hollowknight-hkmultiplayer'):
            if language=='en':assert label not in lang.EN, (key,label)
lang.set_language('fr')

# Explicit library-add choices and cover fallback follow the same language.
for language,title,manual,cover in (
        ('fr','Depuis le catalogue','Manuellement','Jaquette indisponible'),
        ('en','From the catalogue','Manually','Cover unavailable')):
    lang.set_language(language)
    assert lang.tr('Depuis le catalogue')==title
    assert lang.tr('Manuellement')==manual
    assert lang.tr('Jaquette indisponible')==cover
lang.set_language('fr')

for language,label in (('fr','Sélectionnez un jeu'),('en','Select a game')):
    lang.set_language(language)
    assert lang.tr('Sélectionnez un jeu')==label
lang.set_language('fr')

for language,label in (('fr','Lancer'),('en','Launch')):
    lang.set_language(language)
    assert lang.tr('Lancer')==label
lang.set_language('fr')

for language,expected in (
        ('fr','Gamescope : fichiers ouverts autorisés 1024 → 65536 (maximum 1048576).'),
        ('en','Gamescope: open-file limit 1024 → 65536 (hard limit 1048576).')):
    lang.set_language(language)
    assert lang.tr('Gamescope : fichiers ouverts autorisés {p0} → {p1} (maximum {p2}).',
                   p0=1024,p1=65536,p2=1048576)==expected
lang.set_language('fr')

# Uninstall confirmation and preservation guarantees are available in FR/EN.
for language, label in (('fr','DÉSINSTALLER WINDOWS PARTY'),('en','UNINSTALL WINDOWS PARTY')):
    lang.set_language(language)
    assert lang.tr('DÉSINSTALLER WINDOWS PARTY')==label
    assert lang.tr('ANNULER')==('ANNULER' if language=='fr' else 'CANCEL')
    assert lang.tr('Conserve les sauvegardes et les préfixes contenant la progression.')==('Conserve les sauvegardes et les préfixes contenant la progression.' if language=='fr' else 'Keeps saves and prefixes containing player progress.')
    assert context_hints('uninstall-running','keyboard')==[]
lang.set_language('fr')
