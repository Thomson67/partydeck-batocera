# Test : Windows partagé, sauvegardes privées

Les anciennes bottles complètes étaient stockées dans
`/userdata/saves/windows-party/<jeu>/jN/prefixes`. La version test déplace les
bottles et les modifications du contenu vers :

`/userdata/system/wine-bottles/windows-party/players/<identifiant-jeu>/jN/`

Les sauvegardes externalisées par Batocera restent sous
`/userdata/saves/windows-party/<jeu>/jN/windows/`.
Les utilisateurs Wine, registres, réglages et éventuelles sauvegardes internes
au préfixe restent individuels et conservés dans la bottle technique : le
programme ne devine pas qu'un fichier inconnu est jetable.

## Mutualisation

- Une base Windows en lecture seule est extraite par génération de WSquashFS,
  uniquement lorsqu'un préfixe existe. Pour `.wine`, le dossier Windows de la
  source sert directement de base en lecture seule.
- Les fichiers Windows réguliers strictement identiques (contenu, droits,
  propriétaire, date de modification et attributs) sont mutualisés entre
  joueurs, jeux et runners lorsque le disque permet les liens physiques.
- Chaque joueur conserve sa propre vue OverlayFS et ses modifications. Les
  objets partagés ne sont jamais ouverts en écriture par les jeux. Les fichiers
  utilisateurs, registres, données de jeu et sauvegardes ne sont pas mutualisés.
- Le dossier racine du préfixe reste physique, pour rester compatible avec le
  montage WSquashFS natif. Seul son sous-dossier Windows pointe vers la vue du
  joueur. Les copies temporaires UMU conservent ce lien au lieu de recopier
  Windows intégralement.
- L'autorisation de cette vue est ajoutée au contrôleur d'isolation dans les
  vues temporaires des runners UMU. Seuls les chemins Windows de ce joueur
  sont autorisés ; les autres sorties du préfixe restent refusées. L'intégrité
  du script d'origine est vérifiée avant l'adaptation et le manifeste privé est
  actualisé. Aucun runner installé n'est modifié sur l'hôte.
- Les nouvelles installations ne créent pas de `prefixes` dans `saves`. Pour
  les données migrées, un lien de compatibilité conserve les anciens chemins
  absolus. Un explorateur suivant les liens peut afficher une taille cumulée
  supérieure à l'occupation physique réelle. Le bilan Stockage compte les
  blocs alloués et les inodes partagés une seule fois.

## Migration et limites du test

La migration a lieu au lancement du jeu, hors session active. Le disque est
vérifié dans un espace de montage jetable **avant** les déplacements. Une
fusion ambiguë ou un déplacement entre systèmes de fichiers est refusé sans
supprimer les dossiers. Les étapes interrompues sont reprises au lancement
suivant. La mutualisation s'effectue avant le lancement et après la fermeture.
Un premier lancement doit parfois créer le préfixe avant que Windows puisse
être mutualisé.

Les fichiers Windows de plus de 512 Mio, les liens symboliques et les attributs
OverlayFS particuliers sont conservés tels quels. Les sources `.pc` sans
`drive_c/windows` reconnu sont déplacées mais ne reçoivent pas de base Windows
devinée. Les anciennes bases sont conservées ; seuls les objets sans aucun
manifeste ni base les référençant peuvent être nettoyés automatiquement.

Les montages OverlayFS ont été testés réellement en espace de noms Linux :
modifications J1/J2, suppressions, redémarrage, couches inférieures protégées et
copies de préfixes. L'intégration Wine/Proton et Hollow Knight reste à valider
sur Batocera. Cette version est une version test, pas une release stable.

## Test conseillé

1. Fermer tous les jeux et installer la version test.
2. Lancer Hollow Knight à deux joueurs, vérifier progression et réglages de
   chacun, sauvegarder puis quitter normalement.
3. Relancer et vérifier la conservation des deux progressions.
4. Ouvrir **Stockage** : les données techniques sont comptées dans **Bottles**.
   Comparer l'occupation physique avant/après ; ne pas additionner les tailles
   d'un explorateur suivant les liens de compatibilité.
5. En cas d'échec, conserver tous les dossiers et fournir les journaux des deux
   joueurs. Ne pas supprimer les bases/objets : ils font partie des préfixes.

## English

This test moves technical prefixes/content uppers out of the saves tree into
`/userdata/system/wine-bottles/windows-party`. Externalized saves stay under
`saves/windows-party`; registry, users, settings and non-externalized saves stay
private in each player's technical bottle. Only identical Windows system files
are shared through immutable lower layers with per-player copy-on-write views.
UMU materialized prefixes retain the Windows view link. Installed runners are
unchanged; their temporary private isolation helper accepts only that player's
Windows view, with a verified and updated private integrity manifest.

Filesystem support is checked before migration. Existing absolute paths retain
compatibility links. Migration refuses conflicts/cross-filesystem moves and
recovers interrupted renames. Storage counts shared inodes once. Unrecognized
`.pc` Windows layouts remain private; special/oversized Windows files are kept.
Linux OverlayFS isolation/restart tests pass; actual Wine/Proton and Hollow
Knight launches still require Batocera validation. This is a test build.
