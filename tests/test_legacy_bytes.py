"""An input with no annex key gives the bytes it gave before the engine knew annexes (version 0.4.0): the cities that `build` makes, the world built by `assign` in calls, the
worlds built by hand, their world files, documents, chronicles and pictures. The sha256 below were made from a snapshot of the commit of version 0.4.0 (`legacy_bytes.artifacts()`
run on it), so a change that moves one of them is a change to what an old input gives, and is read as that."""

import pytest
from legacy_bytes import artifacts, digest

PINS = {
    "sample grow first=None": "8e3d6772298d46693a6cde120b5a12f298789fa7c43c4d15bef121ee71b4fcd9",
    "sample grow first=0": "f67befe4283dd5ae7e62d7780b869cab995f4d02aab434748ecdbfa9738769c6",
    "sample grow first=41": "d4fc5d402bd3a1b33b9250d406076981370e64473785977facf97eb2da834215",
    "sample grow first=150": "b6a360b76ac8abdb7bdcf8d077bd26490f58d0d683688c446ab0b17f6b9dddfc",
    "sample grow without a coast": "f79da0d026936ee7401b7d7e2d8cd45b52afcbac956eab94a14ba8b131d4b7f8",
    "sample grow picture": "0c1fc445c8bdfa8a8870f91bf5dfa22458aab54e636c1af97f280958cdfb885d",
    "sample grow chronicle": "99a62948d0fb5c3cdc21c131e5dc2e14e1d59eca6a72e9e29f7a010e0a681ff6",
    "sample grow summary": "3a8f60e25ada872ac630e160ce02814d6c71f6f61d68fa814f9402e38f2cd198",
    "sample mirror first=None": "7de26c35417f179a0079c66b54848cd77c3be035e44346c2a7d8c5b3e6b0613b",
    "sample mirror first=0": "5e2b3ee543995a9a4a761d011a54e59c5e32ab7efa731583b93bd202c90d542d",
    "sample mirror first=41": "709cdcd55248c6de6c689752a0a05062eecf689d3f464243ba0445e182741dbd",
    "sample mirror first=150": "b1a51b0ced7c5842fefa234644139325ab20b8344bdbcba2748727e7f3b4e92e",
    "sample mirror without a coast": "3a0d3a7d08ec3c47476e3611d7e82c31ec0cedbbf12b0de0458c7923815d6b83",
    "sample mirror picture": "3f65736dba64f3f5d4ec7c7ec98582fd54b7180ca82c6e4e6d57c8a3e30a4aad",
    "sample mirror chronicle": "56caef4fe4731a32c5779aa59761fd9340713367f8588f804bce166e3db066ea",
    "sample mirror summary": "50938944edcc90bc7f4043dc6cb999f290e1b2f383b3588de9fd0631f4190e5e",
    "sample grow picture of the first 150": "5712aabab05de9985b8407a6e0a1be5332fe287369b10d3001849ff84c47afff",
    "sample items as the reader gives them": "71ff773cc458f3830aec7ca6344067928e805be115b6b322d985887d1fe44754",
    "random world 0 grow": "2abb02db262b47f06db5c818571cbe5a64cff49f15d44652bd81ea491cfc52cb",
    "random world 0 mirror": "5815fac6efc694c73672051781ddcc143b64d6a37190abe98beab14b61d08bbb",
    "random world 1 grow": "44a6d9aa0b577418a4c88837e898ced952c1be55e91f76e4353f930fd9b1adbc",
    "random world 1 mirror": "6ef7a9e282404b1e3130923c5921f767ad962044ec3e770b807ab6f67e60abcc",
    "random world 2 grow": "4c98d6f0c4669d12c02c32068a6294cc8f125dc949a59cdc9ec55f5d6831392e",
    "random world 2 mirror": "944af460011a012b8a9f4f34cbcf794aeb9127706055dae5ecb6a6f699374d99",
    "random world 3 grow": "4ba408f5f7d1a0488bfa706f52279b05f6c18eb8d1ffc91122b65c7d40d96e19",
    "random world 3 mirror": "64553751f6bfa6d70eb55711c85888f082398fda184c75f80a70b6b97c2961bd",
    "random world 4 grow": "9582325f5bbf31ff400a978cb7db0d865703101eba07d4890f8ecb01e435cc46",
    "random world 4 mirror": "9d7cb7f524b38331e50345c58fee49f58c39ea525d3e56082d1f16272b61bd82",
    "random world 5 grow": "a8cdea58d7beb7efc483417180dfae78fbf6bb6a40a79647fd2e11582ead9f65",
    "random world 5 mirror": "f4fbd0e43ea649efff6821a46908c30ee5d2268057777086bc40406c57eef98b",
    "random world 6 grow": "7ac0b41bc1acb1405cf3f18218178c6223f42585d9d298594d4009f0292b6944",
    "random world 6 mirror": "9daa83dee999c805a364efe0e4efe03b8110fd282b0c4b39d48aa9017dedc9a5",
    "random world 7 grow": "f95689862f535bb99000adf5cdbdb46b82b128bfa23bd3d03cced00900493d17",
    "random world 7 mirror": "74bf2eef948c22052b4b8d69054ab62675a44cc9b887b8d43fccd73250f60c55",
    "batched deltas": "70f06721ccbf7c9e26ed41d7e0152e00b8d1dd175134fdc6b094045ea4e566a2",
    "batched world document": "a1a5724cc6544beaa8d9b49938e5ee528b52e9d2f00b4f1cb5459ee196a7ed08",
    "hand scripted world file": "00cdd986d9c25997ee18ef20d8995e1e843f0bbe36d7f93bc9e95e5e7a351ea1",
    "hand scripted city": "9d9c776022e5006a46f58ebce873ce55a01398e387d535edb55418f1adc73fd0",
    "hand scripted world document": "05d9b44df52ad94bac9d664f2813659fdf5e7da8d744774f6c9c04b2d865dd24",
    "hand scripted chronicle": "d1ff8542828bfebcb9bdca8f47540758567aa381c3410d209fd1f153a7e55762",
    "hand scripted_nodes world file": "909c0564d34aca455dab84f7c659faf891f6e3a875d733ac6c1086561d860243",
    "hand scripted_nodes city": "3b6c35a0ef8adccab928b5954f8facbbb27e35d557036911f1095cd38a57e2a7",
    "hand scripted_nodes world document": "1400259f955a23e7cacb6b1870ac7611e2af1c4eec286796379b167b54e10b38",
    "hand scripted_nodes chronicle": "5f0ce179a6eb8dcf1df80649930ed159aed552ec2d284fc6277302b08d50019b",
    "hand scripted_merge world file": "f8ef1194ff53f26e2d908c6e677f8b1fe62507ff89b0780a28028f04aded5274",
    "hand scripted_merge city": "9ea843a3350f0aa994074af6c811336415ac1915cb3589d8c7e4d1506c44c393",
    "hand scripted_merge world document": "dd70dce19e33304ddd8354f38036b42bc1efeea007cb0e489b70b32c0fa14e92",
    "hand scripted_merge chronicle": "4b540f0a8ad1db4b7d8c442522e6ed2b2d88d065d8b1b2c1a8fd800cf6db3b3b",
    "hand scripted_branches world file": "8bca726c6f6558d4b946f76c04a5de67540e528801c1fd600711e893886b5faf",
    "hand scripted_branches city": "7a632e07d7cc15c12c6a1acc231c0df6042845c89a4a66be7acc8d3c6d382692",
    "hand scripted_branches world document": "2301d7cd12780b3555f010bcca27c4cf8d524a8571a59ae3ed8f983b0f3707a3",
    "hand scripted_branches chronicle": "55a774974f3892c84ae2bdd5d60cae0fe19af295abedd1f05c816b27ffcea741",
    "hand every entry world file": "8c04dbf46f5440f0d9787767cf36f2a08aad133b7bfd1373de7859efe8fa70f8",
    "hand every entry city": "7f9bdee4d0b90b847c09244eee059aca04bd7939b93dcb374922dfb3c6e1d87f",
    "hand every entry world document": "d909d2788770d7f1064a44350b8404eb812a8ba7d3f0e543b117852f57403959",
    "hand every entry chronicle": "3d7effffa27257aace4c4568d69518cbeaa1bb3b223a288166af95cbe8b465ea",
    "hand scripted picture": "fb10760d5c26741f42d97b2528ce2d8c188fa3567026f8167bc923b7baa8787d",
    "hand play 3 world file": "7d1a4fbb107df24135b5891a62a3688a34af10fc222e8b55c69e33229bd33ee4",
    "hand play 3 city": "13639ecd558cf16fe9b2380edd78d33c99d76db4e870b3aceba708c21edd8e81",
    "hand play 5 world file": "b26fa8bbee839679ee471b008c95e2132c2ddf44d6742102e85b954a102ec764",
    "hand play 5 city": "c42c710c0d15a75bfc0f5542051958fbe2db9aca2a19e122a6ddc2c8f67ab056",
    "hand play 7 world file": "fafe9b5f2f690375177bc300bca9c97b4bac23a7d73bca1d7f1d0104a99f076a",
    "hand play 7 city": "656ac4206eb80898aaf85c01257af48b51e39bae13aaad5890272efc5018f586",
    "hand play 11 world file": "5000e1d40a44a9abbec62101e38192021e1a809888772936a32bb62f7eb02b09",
    "hand play 11 city": "3145881a92edc449198b73b7ee73a05346f4d58325cf458fe378a148f919dcaa",
}


@pytest.fixture(scope="module")
def made():
    return {name: digest(text) for name, text in artifacts().items()}


def test_the_pins_and_the_cases_are_the_same_names(made):
    assert list(made) == list(PINS)


def test_every_case_has_a_text_of_its_own(made):
    assert len(set(PINS.values())) == len(PINS) and all(len(pin) == 64 for pin in PINS.values())


@pytest.mark.parametrize("name", list(PINS))
def test_an_input_with_no_annex_key_gives_the_bytes_of_version_0_4_0(made, name):
    assert made[name] == PINS[name]
