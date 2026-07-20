# Requirements Document

## Introduction

The Biometric Device Manager enables administrators to remotely control Arduino-based fingerprint scanners from the Django web dashboard. It covers device registration, mode switching, fingerprint enrollment/deletion, live progress monitoring via AJAX polling, a Hardware Service layer isolating serial communication from business logic, and full audit logging of all device commands and events.

## Glossary

- **BiometricDevice**: An Arduino-based fingerprint scanner registered in the system, identified by a unique `device_id`.
- **DeviceCommand**: A structured instruction sent from Django to a BiometricDevice (e.g. ENROLL, DELETE, RESTART).
- **DeviceEvent**: A timestamped record of a message received from a BiometricDevice (e.g. enrollment progress, attendance match, error).
- **EnrollmentRequest**: A lifecycle record tracking an admin-initiated fingerprint registration for a specific Employee.
- **HardwareService**: The service layer responsible for all serial communication with BiometricDevices, isolating hardware I/O from Django business logic.
- **FingerprintBridge**: The standalone Python process running on the host machine that reads from the serial port and relays commands/events to/from the Django API.
- **Fingerprint ID**: An integer (1–127) stored on the Arduino that maps to an Employee in Django.
- **Communication Protocol**: The text-based serial protocol used between Django/Bridge and the Arduino (e.g. `ENROLL:5`, `DELETE:5`, `RESTART`).
- **AJAX Polling**: A browser technique where the frontend periodically calls a Django JSON endpoint to retrieve updated enrollment status.
- **Admin**: An authenticated Django user with access to the device management dashboard pages.

---

## Requirements

### Requirement 1 — Device Registration and Management

**User Story:** As an admin, I want to register and manage biometric devices, so that I can track which devices are connected and their current state.

#### Acceptance Criteria

1. WHEN an admin submits a valid device registration form, THE Device Manager SHALL create a BiometricDevice record with `device_id`, `name`, `serial_port`, `baudrate`, and initial status `OFFLINE`.
2. WHEN an admin views the device list page, THE Device Manager SHALL display each device's name, device_id, serial_port, status, mode, template_count, and last_seen_at.
3. WHEN an admin edits a device record, THE Device Manager SHALL update the stored configuration fields and record the updated_at timestamp.
4. IF a registration form is submitted with a duplicate `device_id`, THEN THE Device Manager SHALL reject the submission and return a validation error identifying the conflicting field.

---

### Requirement 2 — Device Mode Control

**User Story:** As an admin, I want to switch a device between operating modes, so that I can prepare it for enrollment, deletion, or normal attendance operation.

#### Acceptance Criteria

1. WHEN an admin issues an ENROLL command for an employee, THE Device Manager SHALL create a DeviceCommand record with command type `ENROLL`, link it to the EnrollmentRequest, and set the command status to `QUEUED`.
2. WHEN an admin issues a DELETE command for a fingerprint ID, THE Device Manager SHALL create a DeviceCommand record with command type `DELETE` and the target fingerprint ID in the payload.
3. WHEN an admin issues a RESTART command, THE Device Manager SHALL create a DeviceCommand record with command type `RESTART` and set the device status to `BUSY`.
4. WHEN an admin issues an ATTENDANCE_MODE command, THE Device Manager SHALL create a DeviceCommand record with command type `ATTENDANCE_MODE` and update the device mode to `ATTENDANCE` upon acknowledgement.
5. WHEN an admin issues a DEVICE_STATUS command, THE Device Manager SHALL create a DeviceCommand record with command type `DEVICE_STATUS` and update the device's `template_count`, `firmware_version`, and `last_seen_at` upon response.

---

### Requirement 3 — Fingerprint Enrollment Workflow

**User Story:** As an admin, I want to register an employee's fingerprint through the dashboard, so that the employee can use the biometric scanner for attendance.

#### Acceptance Criteria

1. WHEN an admin initiates enrollment for an employee, THE Device Manager SHALL create an EnrollmentRequest with status `PENDING` and assign an unused fingerprint ID (1–127).
2. WHEN the FingerprintBridge polls the enrollment queue and picks up a PENDING request, THE Device Manager SHALL transition the EnrollmentRequest status from `PENDING` to `DISPATCHED` and record `dispatched_at`.
3. WHEN the Arduino reports enrollment progress, THE Device Manager SHALL update the EnrollmentRequest `progress_message` field and create a DeviceEvent of type `ENROLL_PROGRESS`.
4. WHEN the Arduino reports a successful enrollment, THE Device Manager SHALL set the EnrollmentRequest status to `COMPLETED`, set `completed_at`, and update the Employee's `fingerprint_id`.
5. IF the Arduino reports an enrollment error, THEN THE Device Manager SHALL set the EnrollmentRequest status to `FAILED`, record the `error_message`, and create a DeviceEvent of type `ERROR`.
6. WHILE an EnrollmentRequest is in `DISPATCHED` or `IN_PROGRESS` status, THE Device Manager SHALL reject new enrollment requests for the same employee.

---

### Requirement 4 — Fingerprint Deletion

**User Story:** As an admin, I want to delete an employee's fingerprint from a device, so that I can revoke biometric access or re-enroll with a new template.

#### Acceptance Criteria

1. WHEN an admin deletes a fingerprint for an enrolled employee, THE Device Manager SHALL create a DeviceCommand of type `DELETE` with the employee's `fingerprint_id` in the payload.
2. WHEN the Arduino confirms successful deletion, THE Device Manager SHALL create a DeviceEvent of type `DELETE_SUCCESS`, clear the Employee's `fingerprint_id`, and set the DeviceCommand status to `COMPLETED`.
3. IF a delete command is issued for an employee with no `fingerprint_id`, THEN THE Device Manager SHALL reject the request and return a validation error.
4. WHEN an admin re-registers a fingerprint after deletion, THE Device Manager SHALL follow the standard enrollment workflow defined in Requirement 3.

---

### Requirement 5 — Hardware Service Layer

**User Story:** As a developer, I want a Hardware Service layer between Django views and serial communication, so that device I/O is isolated and testable independently of HTTP request handling.

#### Acceptance Criteria

1. THE HardwareService SHALL expose methods: `enroll(employee, fingerprint_id)`, `delete(fingerprint_id)`, `restart()`, `get_status()`, and `set_attendance_mode()`, each returning a DeviceCommand instance.
2. WHEN a HardwareService method is called, THE HardwareService SHALL create and persist a DeviceCommand record before any serial write is attempted.
3. WHEN the FingerprintBridge receives a serial message, THE HardwareService SHALL parse it into a typed DeviceEvent record and persist it with `device_id`, `event_type`, `fingerprint_id` (if applicable), `message`, and `created_at`.
4. IF the serial port is unavailable, THEN THE HardwareService SHALL record a DeviceEvent of type `ERROR` and set the device status to `OFFLINE` without raising an unhandled exception to the calling view.

---

### Requirement 6 — Communication Protocol Serialization

**User Story:** As a developer, I want a defined serial communication protocol between Django and the Arduino, so that commands and responses are structured and parseable.

#### Acceptance Criteria

1. WHEN the HardwareService sends a command, THE Device Manager SHALL serialize it to the text format `COMMAND:PARAM` (e.g. `ENROLL:5`, `DELETE:5`) terminated with a newline character.
2. WHEN the FingerprintBridge receiv

---ashboard. Dagere Manevic in the Dce the errorrfaand sud`, rint_iingerpting `frve the exis, preseation-registr reort theem SHALL abSystN THE ils, THEfaistration -regf ree ohas DELETE pIF theaction.
3. admin interurther hout fnd witROLL comma ENtch thed dispaanquest Re Enrollmentreate anomatically cm SHALL aut THE Systeccessfully, sun completesregistratiof re-phase oDELETE  the  WHENon.
2.sful deletipon succes uROLL commandy a new ENollowed brint_id` fgerpin`fhe existing d for tETE comman DEL issue a firsttem SHALLd`, THE Sysngerprint_ias a `fio already hee wh an employt" forrprinr Fingeegiste"Re-ricks min cl an ad
1. WHENriteria
ce C### Acceptan

#s.eletion stepanual d without mct template or incorremageda dacan replace  that I  employee so anint forerprfingregister a o re- tdmin, I wanty:** As an aUser Stor

**ent 3uirem### Req---



or text.with the errOR of type ERRDeviceEvent  store a  andEDAILs to Fnd statueviceComma set the Dstem SHALLE Syd, THEN THTE comman to a DELEnseOR:` responds an `ERRuino se IF the ArdSUCCESS.
4.ELETE_ Dt of typeen a DeviceEv, and storeull) (set to nnt_id` fieldfingerpriloyee's `Emplear the LETED, cto COMPmand status viceComDethe L set  SHALem>`, THE Systrprint_id:<fingeDELETEACK:no sends ` the ArduiNT.
3. WHENSEstatus to e command thet uino and sthe Ardand to commid>` erprint_ETE:<fingDELLL send a ` SHAceare Servi, THE Hardwspatcheddid is viceCommanLETE De WHEN a DE2..
payloads the print_id` aers `finge'loyeth the empELETE wif type DeCommand oa Deviccreate  SHALL E Systemashboard, THer DDevice Managoyee on the mplor an e" frprintge"Delete Finmin clicks an adWHEN . iteria

1e CrAcceptanc
#### ess.
has accer oyee no longled empl or re-enrolerminated te so that aom the devic frrintfingerployee's e an empletI want to des an admin, r Story:** A2

**Userement Requi
### --

-
ance Mode.tendto AtArduino return the mmand to _MODE` co `ATTENDANCE anSHALL sendce Servi Hardware ails, THE fcompletes or enrollment  WHENRROR.
6. EtypeEvent of  Devicere age`, and sto`error_messatext in rror ore the e FAILED, st status toequestmentR the EnrollHALL settem SHEN THE Syslment, Tenrolng e duriR:` messagan `ERROds Arduino sen
5. IF the OLL_SUCCESS.e ENR of typceEventstore a Devialue, and med vhe confir` to tgerprint_id's `finyeet the EmploTED, seus to COMPLEtatuest snrollmentReqet the ESHALL sTHE System _id>`, <fingerprintCESS_ENROLL:nds `SUC Arduino setheN SS.
4. WHEREOLL_PROGENR of type enticeEvore a Dev st ande` fieldress_messag `progest'sllmentRequEnro the ateupdSHALL ystem ), THE Sfinger`ace FO:Pl., `INent (e.ging enrollmdurs message a progress uino sendthe Ard. WHEN tion.
3nnecial co the seroveruino  the Ardcommand tod>` rint_iL:<fingerpOLNR `Ed an senLL Service SHAardwareE Hists, THRequest exollmentNDING Enr2. WHEN a PE
evice.iometricD and Bployeeselected emthe with  it associateDING and  status PENuest withntReqlmenroln Ereate aL cHALE System S THoard,ashbanager DDevice Mthe on " rprintinger Fs "Registed clickployee ans an em selectadminWHEN an 

1.  Criteriace### Acceptananner.

#c scbiometrithe by d dentifiebe iyee can at the emploployee so thnt for an emprifingerster a new  to regiI wantan admin, y:** As er Stort 1

**Usen# Requirements

### Requirem
---

#.
ngee raat and dent type by evlefilterab device, ica specifecords for eEvent rew of Devic vinatedog**: A pagion Latiic **Communeries.
-d status qu, anont, deletir enrollmenrols forovides cont and pDevicesmetriced Bioregistert lists all es/` tha/devicage at `web prd**: The Dashboaager evice Man
- **Dstate.ve updated receils to  intervaint at shortndpo JSON es aedly callser repeatthe browe where echniquide tA client-sg**: inAJAX Poll
- **b UI. the we toedrelay again") , "Placenger"emove fi", "Ringer "Place fent (e.g.,rollmen during  the Arduino byntg serindable steaan-re**: A humress Messag*Prog
- *OR:`).OLL:`, `ERRSUCCESS_ENR., `ACK:`, `x (e.g by prefiedes pars\n`, responsARAMs `CMD:Pds sent aommanrial: cr set used ovext formaII teminated ASC newline-ter*: AProtocol*mand om **CNANCE.
-, or MAINTE DELETIONLLMENT,DANCE, ENROENATTan Arduino: tate of perating scurrent oe *: Th **Mode*ory.
-ensor memo's she Arduin in toredlate stemp tinta fingerprentifies niquely id that uer (1–127)eg int**: Anrint ID
- **Fingerped events.ucturnses to strspos and raw reto raw bytends commaured lates structon and transnnecti serial coat owns theice`) threServwa`Hard (assservice cl Python ice**: Aardware Servled.
- **Hed or faicompleto nding tom pequest frn reatio registrprintfingerof a  lifecycle he fullcking ttraango model : A Djt**equesllmentR
- **Enront type.ed evecategorizd  anamp a timest logged withricDevice,a Biometed from ge receivd messainbounesenting an reprl ngo modent**: A DjaeEveic
- **DevcDevice.o a Biometrint t and sequeued, RESTART) VICE_STATUS DEE, VERIFY, DELETd (ENROLL,manured com structg apresentingo model re: A Djanmand***DeviceCom.
- *erial_port` and a `s`device_id`e qua unitified by ideno unit, Arduind  a registeresentingel repreo modDjangA ice**: cDeviometrition.
- **Bconnecial (USB) er a seres ov